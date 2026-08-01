"""建立一台 RDS PostgreSQL，並把連線資訊寫進 repo 根目錄的 .env。

做的事情：
  1. 抓你目前的公網 IP
  2. 建一個 Security Group，只允許「你這個 IP」連 5432
  3. 建 db.t3.micro 的 PostgreSQL 實例（公開可連線）
  4. 等它 available，把 host / port / user / password 寫回 .env

為什麼設成「公開可連線」？
  這樣你本機就能直接用 psycopg 灌資料、用 DBeaver 之類的工具看資料，
  不用先處理 VPC 內的跳板機。代價是這台 DB 暴露在網際網路上，
  所以 Security Group 只開你的 IP。這只適合 workshop 帳號的臨時 demo，
  正式環境要放在私有子網並透過 VPC 內的服務存取。

執行（從 repo 根目錄）：
    .venv\\Scripts\\python.exe packages\\api\\scripts\\rds_create.py

其他用法：
    --status    只查現況，不建立
    --delete    刪掉這台 RDS（用完務必執行，會一直計費）
"""

from __future__ import annotations

import argparse
import secrets
import string
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import boto3  # noqa: E402
from botocore.exceptions import ClientError  # noqa: E402

from op_agent.config import config  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[3]
ENV_PATH = REPO_ROOT / ".env"

DB_ID = "op-life-agent-db"
DB_NAME = "oplifeagent"
DB_USER = "opadmin"
SG_NAME = "op-life-agent-db-sg"
INSTANCE_CLASS = "db.t3.micro"
ENGINE_VERSION = "17.10"
STORAGE_GB = 20

rds = boto3.client("rds", region_name=config.region)
ec2 = boto3.client("ec2", region_name=config.region)


def my_public_ip() -> str:
    """AWS 自己提供的 IP 查詢服務，回傳純文字。"""
    with urllib.request.urlopen("https://checkip.amazonaws.com", timeout=10) as res:
        return res.read().decode().strip()


def default_vpc_id() -> str:
    vpcs = ec2.describe_vpcs(Filters=[{"Name": "isDefault", "Values": ["true"]}])["Vpcs"]
    if not vpcs:
        raise SystemExit("找不到預設 VPC，需要先建 VPC（hackathon 不建議走這條路）")
    return vpcs[0]["VpcId"]


def ensure_security_group(vpc_id: str, my_ip: str) -> str:
    """建立（或沿用）Security Group，並確保只有我的 IP 能連 5432。"""
    existing = ec2.describe_security_groups(
        Filters=[{"Name": "group-name", "Values": [SG_NAME]}, {"Name": "vpc-id", "Values": [vpc_id]}]
    )["SecurityGroups"]

    if existing:
        sg_id = existing[0]["GroupId"]
        print(f"  沿用既有 Security Group {sg_id}")
    else:
        sg_id = ec2.create_security_group(
            GroupName=SG_NAME,
            Description="OpenPoint life agent RDS - only my IP",
            VpcId=vpc_id,
        )["GroupId"]
        print(f"  建立 Security Group {sg_id}")

    cidr = f"{my_ip}/32"
    try:
        ec2.authorize_security_group_ingress(
            GroupId=sg_id,
            IpPermissions=[
                {
                    "IpProtocol": "tcp",
                    "FromPort": 5432,
                    "ToPort": 5432,
                    "IpRanges": [{"CidrIp": cidr, "Description": "my laptop"}],
                }
            ],
        )
        print(f"  已開放 {cidr} 連 5432")
    except ClientError as err:
        if err.response["Error"]["Code"] == "InvalidPermission.Duplicate":
            print(f"  {cidr} 的規則已存在")
        else:
            raise
    return sg_id


def generate_password() -> str:
    """RDS 密碼不可含 / @ " 與空白。"""
    alphabet = string.ascii_letters + string.digits + "-_#%^*+=."
    return "".join(secrets.choice(alphabet) for _ in range(24))


def describe() -> dict | None:
    try:
        return rds.describe_db_instances(DBInstanceIdentifier=DB_ID)["DBInstances"][0]
    except ClientError as err:
        if err.response["Error"]["Code"] == "DBInstanceNotFound":
            return None
        raise


def upsert_env(values: dict[str, str]) -> None:
    """把 key=value 寫回 .env（已存在的 key 就更新，不存在就附加）。"""
    lines = ENV_PATH.read_text(encoding="utf-8").splitlines() if ENV_PATH.exists() else []
    for key, val in values.items():
        replaced = False
        for i, line in enumerate(lines):
            if line.strip().startswith(f"{key}="):
                lines[i] = f"{key}={val}"
                replaced = True
                break
        if not replaced:
            lines.append(f"{key}={val}")
    ENV_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"  已更新 {ENV_PATH}")


def wait_available(timeout_s: int = 900) -> dict:
    print("\n等待 RDS 變成 available（第一次建立通常 5~10 分鐘）…")
    started = time.time()
    last = ""
    while time.time() - started < timeout_s:
        db = describe()
        if db is None:
            raise SystemExit("實例不見了？")
        status = db["DBInstanceStatus"]
        if status != last:
            print(f"  [{int(time.time() - started):>4}s] 狀態：{status}")
            last = status
        if status == "available":
            return db
        time.sleep(15)
    raise SystemExit("等太久了，請稍後用 --status 再查")


def do_status() -> int:
    db = describe()
    if db is None:
        print(f"沒有名為 {DB_ID} 的 RDS 實例。")
        return 0
    ep = db.get("Endpoint") or {}
    print(f"識別碼   : {db['DBInstanceIdentifier']}")
    print(f"狀態     : {db['DBInstanceStatus']}")
    print(f"引擎     : {db['Engine']} {db.get('EngineVersion')}")
    print(f"端點     : {ep.get('Address', '(還沒配置)')}:{ep.get('Port', '-')}")
    print(f"公開連線 : {db.get('PubliclyAccessible')}")
    print(f"資料庫名 : {db.get('DBName')}")
    return 0


def do_delete() -> int:
    db = describe()
    if db is None:
        print("本來就沒有這台 RDS，不用刪。")
        return 0
    print(f"即將刪除 {DB_ID}（不保留最終快照，資料會全部消失）")
    rds.delete_db_instance(
        DBInstanceIdentifier=DB_ID, SkipFinalSnapshot=True, DeleteAutomatedBackups=True
    )
    print("刪除指令已送出，背景執行約 3~5 分鐘。用 --status 追蹤。")
    print("提醒：Security Group 不會一起刪，需要的話手動移除 " + SG_NAME)
    return 0


def do_create() -> int:
    existing = describe()
    if existing:
        print(f"{DB_ID} 已經存在，狀態 {existing['DBInstanceStatus']}，跳過建立。")
        if existing["DBInstanceStatus"] != "available":
            existing = wait_available()
        ep = existing["Endpoint"]
        print(f"\n端點：{ep['Address']}:{ep['Port']}")
        print("密碼在 .env 的 PGPASSWORD（如果找不到就用 --delete 砍掉重建）")
        return 0

    print("=" * 66)
    print("建立 RDS PostgreSQL")
    print("=" * 66)
    print(f"  region         : {config.region}")
    print(f"  識別碼         : {DB_ID}")
    print(f"  規格           : {INSTANCE_CLASS}  儲存 {STORAGE_GB}GB")
    print(f"  引擎           : postgres {ENGINE_VERSION}")
    print("  預估費用       : 約 US$0.02/小時（用完請執行 --delete）")
    print()

    ip = my_public_ip()
    print(f"  你的公網 IP    : {ip}")
    vpc = default_vpc_id()
    print(f"  預設 VPC       : {vpc}")
    sg_id = ensure_security_group(vpc, ip)

    password = generate_password()
    print("\n建立實例中…")
    rds.create_db_instance(
        DBInstanceIdentifier=DB_ID,
        DBName=DB_NAME,
        DBInstanceClass=INSTANCE_CLASS,
        Engine="postgres",
        EngineVersion=ENGINE_VERSION,
        MasterUsername=DB_USER,
        MasterUserPassword=password,
        AllocatedStorage=STORAGE_GB,
        StorageType="gp3",
        VpcSecurityGroupIds=[sg_id],
        PubliclyAccessible=True,
        BackupRetentionPeriod=0,  # demo 不需要自動備份，省錢也省時間
        MultiAZ=False,
        AutoMinorVersionUpgrade=True,
        DeletionProtection=False,  # 方便你之後砍掉
        Tags=[
            {"Key": "Project", "Value": "openpoint-life-agent"},
            {"Key": "Purpose", "Value": "hackathon-demo"},
        ],
    )

    db = wait_available()
    ep = db["Endpoint"]

    upsert_env(
        {
            "PGHOST": ep["Address"],
            "PGPORT": str(ep["Port"]),
            "PGDATABASE": DB_NAME,
            "PGUSER": DB_USER,
            "PGPASSWORD": password,
        }
    )

    print("\n" + "=" * 66)
    print("完成")
    print("=" * 66)
    print(f"  端點 : {ep['Address']}:{ep['Port']}")
    print(f"  資料庫 : {DB_NAME}   使用者 : {DB_USER}")
    print("  密碼已寫進 .env（.env 有被 gitignore，不會進版控）")
    print("\n下一步：")
    print("  .venv\\Scripts\\python.exe packages\\api\\scripts\\rds_load.py")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="建立／查詢／刪除 demo 用的 RDS PostgreSQL")
    parser.add_argument("--status", action="store_true", help="只查現況")
    parser.add_argument("--delete", action="store_true", help="刪除實例（會計費，用完請執行）")
    args = parser.parse_args()

    if args.status:
        return do_status()
    if args.delete:
        return do_delete()
    return do_create()


if __name__ == "__main__":
    raise SystemExit(main())
