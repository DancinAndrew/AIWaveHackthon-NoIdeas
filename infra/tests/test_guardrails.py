from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from infra.guardrails import (
    GuardrailViolation,
    scan_allowed_file,
    validate_cloudformation,
    validate_upload_manifest,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
UTILITY_KB_FILES = [
    f"data/mock/knowledge_base/utility_repair/{stem}{suffix}"
    for stem in ("01-safety", "02-sop", "03-notice", "04-terms", "05-faq")
    for suffix in (".md", ".md.metadata.json")
]


def safe_template() -> dict[str, object]:
    return {
        "Resources": {
            "KnowledgeBucket": {
                "Type": "AWS::S3::Bucket",
                "Properties": {
                    "PublicAccessBlockConfiguration": {
                        "BlockPublicAcls": True,
                        "BlockPublicPolicy": True,
                        "IgnorePublicAcls": True,
                        "RestrictPublicBuckets": True,
                    }
                },
            },
            "Database": {
                "Type": "AWS::RDS::DBInstance",
                "Properties": {"PubliclyAccessible": False},
            },
            "ApplicationSecurityGroup": {
                "Type": "AWS::EC2::SecurityGroup",
                "Properties": {
                    "SecurityGroupIngress": [
                        {
                            "IpProtocol": "tcp",
                            "FromPort": 443,
                            "ToPort": 443,
                            "CidrIp": "10.0.0.0/16",
                        }
                    ]
                },
            },
            "Supervisor": {
                "Type": "AWS::Lambda::Function",
                "Properties": {
                    "Environment": {
                        "Variables": {
                            "BEDROCK_MODEL_ID": "amazon.nova-2-lite-v1:0"
                        }
                    }
                },
            },
        }
    }


class CloudFormationGuardrailTests(unittest.TestCase):
    def test_safe_template_passes(self) -> None:
        validate_cloudformation(safe_template())

    def test_s3_bucket_requires_all_public_access_blocks(self) -> None:
        template = safe_template()
        bucket = template["Resources"]["KnowledgeBucket"]  # type: ignore[index]
        bucket["Properties"]["PublicAccessBlockConfiguration"].pop(  # type: ignore[index]
            "RestrictPublicBuckets"
        )

        with self.assertRaisesRegex(GuardrailViolation, "RestrictPublicBuckets"):
            validate_cloudformation(template)

    def test_rds_cannot_be_public(self) -> None:
        template = safe_template()
        database = template["Resources"]["Database"]  # type: ignore[index]
        database["Properties"]["PubliclyAccessible"] = True  # type: ignore[index]

        with self.assertRaisesRegex(GuardrailViolation, "PubliclyAccessible"):
            validate_cloudformation(template)

    def test_security_group_cannot_be_open_to_the_world(self) -> None:
        for cidr_key, cidr in (("CidrIp", "0.0.0.0/0"), ("CidrIpv6", "::/0")):
            with self.subTest(cidr=cidr):
                template = safe_template()
                security_group = template["Resources"][  # type: ignore[index]
                    "ApplicationSecurityGroup"
                ]
                ingress = security_group["Properties"]["SecurityGroupIngress"][0]  # type: ignore[index]
                ingress.pop("CidrIp", None)
                ingress[cidr_key] = cidr

                with self.assertRaisesRegex(GuardrailViolation, cidr.replace("/", "/")):
                    validate_cloudformation(template)

    def test_prohibited_compute_resources_are_rejected(self) -> None:
        prohibited = (
            "AWS::EC2::Instance",
            "AWS::EMR::Cluster",
            "AWS::SageMaker::TrainingJob",
        )
        for resource_type in prohibited:
            with self.subTest(resource_type=resource_type):
                template = safe_template()
                template["Resources"]["Unexpected"] = {  # type: ignore[index]
                    "Type": resource_type,
                    "Properties": {},
                }

                with self.assertRaisesRegex(GuardrailViolation, resource_type):
                    validate_cloudformation(template)

    def test_only_the_approved_bedrock_model_is_allowed(self) -> None:
        template = safe_template()
        function = template["Resources"]["Supervisor"]  # type: ignore[index]
        function["Properties"]["Environment"]["Variables"][  # type: ignore[index]
            "BEDROCK_MODEL_ID"
        ] = "anthropic.some-unapproved-model"

        with self.assertRaisesRegex(GuardrailViolation, "unapproved-model"):
            validate_cloudformation(template)


class UploadGuardrailTests(unittest.TestCase):
    def test_curated_utility_knowledge_base_manifest_passes(self) -> None:
        manifest = json.loads(
            (REPOSITORY_ROOT / "infra/upload-manifest.json").read_text(
                encoding="utf-8"
            )
        )

        self.assertEqual(sorted(manifest["files"]), sorted(UTILITY_KB_FILES))
        validate_upload_manifest(REPOSITORY_ROOT, manifest)

    def test_manifest_rejects_non_curated_sources(self) -> None:
        for prohibited_path in (
            "data/mock/cases/pii_vault.json",
            "data/competition/AWS_AI_League_Hackathon_Problem_Statement.pdf",
        ):
            with self.subTest(path=prohibited_path):
                with self.assertRaisesRegex(GuardrailViolation, "not approved"):
                    validate_upload_manifest(
                        REPOSITORY_ROOT,
                        {"files": UTILITY_KB_FILES + [prohibited_path]},
                    )

    def test_scanner_rejects_real_pii_and_payment_identifiers(self) -> None:
        samples = {
            "email.md": "請聯絡 resident@example.com",
            "mobile.md": "住戶電話 0912-345-678",
            "card.md": "卡號 4111 1111 1111 1111",
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for filename, content in samples.items():
                with self.subTest(filename=filename):
                    path = root / filename
                    path.write_text(content, encoding="utf-8")
                    with self.assertRaises(GuardrailViolation):
                        scan_allowed_file(path)

    def test_scanner_rejects_executable_content(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "malware.md"
            path.write_bytes(b"\x7fELF" + b"\x00" * 32)

            with self.assertRaisesRegex(GuardrailViolation, "executable"):
                scan_allowed_file(path)

    def test_benign_policy_words_do_not_trigger_false_positive(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "terms.md"
            path.write_text(
                "地址僅供派工；付款在報價確認後處理；手機欄位不得上傳知識庫。",
                encoding="utf-8",
            )

            scan_allowed_file(path)


if __name__ == "__main__":
    unittest.main()
