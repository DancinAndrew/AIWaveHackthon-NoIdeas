"""探測這個 AWS 帳號的網路與 RDS 現況，決定 RDS 部署方案可不可行。

執行（從 repo 根目錄）：
    .venv\\Scripts\\python.exe packages\\api\\scripts\\probe_rds.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import boto3  # noqa: E402
from botocore.exceptions import ClientError  # noqa: E402

from op_agent.config import config  # noqa: E402


def section(title: str) -> None:
    print()
    print("=" * 66)
    print(title)
    print("=" * 66)


def safe(label: str, fn):
    try:
        return fn()
    except ClientError as err:
        code = err.response.get("Error", {}).get("Code", "?")
        print(f"  [{label}] 失敗：{code} — {err.response.get('Error', {}).get('Message', '')[:160]}")
        return None
    except Exception as err:  # noqa: BLE001
        print(f"  [{label}] 失敗：{type(err).__name__}: {err}")
        return None


def main() -> int:
    region = config.region
    print(f"region = {region}")
    ec2 = boto3.client("ec2", region_name=region)
    rds = boto3.client("rds", region_name=region)

    section("1) VPC")
    vpcs = safe("describe_vpcs", lambda: ec2.describe_vpcs()["Vpcs"])
    default_vpc = None
    if vpcs is not None:
        for v in vpcs:
            flag = "（預設 VPC）" if v.get("IsDefault") else ""
            print(f"  {v['VpcId']}  {v['CidrBlock']}  {flag}")
            if v.get("IsDefault"):
                default_vpc = v["VpcId"]
        if not vpcs:
            print("  沒有任何 VPC")

    section("2) Subnet（RDS 至少需要 2 個不同 AZ 的子網）")
    subnets = safe("describe_subnets", lambda: ec2.describe_subnets()["Subnets"])
    public_by_az: dict[str, list[str]] = {}
    if subnets is not None:
        for s in subnets:
            auto_ip = s.get("MapPublicIpOnLaunch")
            kind = "公有(自動配 IP)" if auto_ip else "私有/無自動 IP"
            print(f"  {s['SubnetId']}  {s['AvailabilityZone']}  {s['CidrBlock']}  {kind}  vpc={s['VpcId']}")
            if auto_ip:
                public_by_az.setdefault(s["AvailabilityZone"], []).append(s["SubnetId"])
        print(f"\n  公有子網涵蓋 {len(public_by_az)} 個 AZ")

    section("3) 現有 RDS 實例")
    dbs = safe("describe_db_instances", lambda: rds.describe_db_instances()["DBInstances"])
    if dbs is not None:
        if not dbs:
            print("  目前沒有任何 RDS 實例")
        for d in dbs:
            ep = d.get("Endpoint") or {}
            print(
                f"  {d['DBInstanceIdentifier']}  {d['Engine']} {d.get('EngineVersion')}  "
                f"{d['DBInstanceStatus']}  public={d.get('PubliclyAccessible')}  "
                f"{ep.get('Address', '-')}:{ep.get('Port', '-')}"
            )

    section("4) 可用的 PostgreSQL 版本（挑最新的用）")
    vers = safe(
        "describe_db_engine_versions",
        lambda: rds.describe_db_engine_versions(Engine="postgres")["DBEngineVersions"],
    )
    if vers:
        latest = [v["EngineVersion"] for v in vers][-6:]
        print("  " + ", ".join(latest))

    section("5) 能不能建 RDS？（用 dry-run 式探測：故意用非法參數看被擋在哪一關）")
    try:
        rds.create_db_instance(
            DBInstanceIdentifier="op-permission-probe-do-not-create",
            DBInstanceClass="db.t3.micro",
            Engine="postgres",
            MasterUsername="probe",
            MasterUserPassword="x",  # 故意太短 -> 若權限 OK 會回 InvalidParameterValue
            AllocatedStorage=20,
        )
        print("  !! 竟然建立成功了，請立刻刪除 op-permission-probe-do-not-create")
    except ClientError as err:
        code = err.response.get("Error", {}).get("Code", "?")
        msg = err.response.get("Error", {}).get("Message", "")
        if code in ("AccessDenied", "AccessDeniedException", "UnauthorizedOperation"):
            print(f"  ✗ 沒有建立 RDS 的權限：{msg[:200]}")
        elif code in ("InvalidParameterValue", "InvalidParameterCombination"):
            print(f"  ✓ 有權限（被參數驗證擋下，不是被權限擋下）：{msg[:120]}")
        else:
            print(f"  ? 其他錯誤 {code}：{msg[:200]}")

    section("6) Secrets Manager（存 DB 密碼用）")
    sm = boto3.client("secretsmanager", region_name=region)
    safe("list_secrets", lambda: print(f"  可讀取，目前有 {len(sm.list_secrets()['SecretList'])} 個 secret"))

    section("結論建議")
    if default_vpc:
        print(f"  有預設 VPC（{default_vpc}），公有子網 {len(public_by_az)} 個 AZ")
        if len(public_by_az) >= 2:
            print("  → 可以建「公開可連線」的 RDS，本機 psql / python 直接灌資料，最省事")
        else:
            print("  → 公有子網不足 2 個 AZ，需要自己建子網群組")
    else:
        print("  沒有預設 VPC，要自己開 VPC + 子網 + 路由表，hackathon 不建議")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
