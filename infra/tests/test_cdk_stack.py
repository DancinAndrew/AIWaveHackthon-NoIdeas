from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from typing import Any


os.environ.setdefault("JSII_RUNTIME_PACKAGE_CACHE", "/tmp/aiwave-jsii-cache")
os.environ.setdefault("JSII_SILENCE_WARNING_UNTESTED_NODE_VERSION", "1")

from aws_cdk import App, Environment  # noqa: E402
from aws_cdk.assertions import Template  # noqa: E402

from infra.aiwave_stack import (  # noqa: E402
    AiwaveStagingStack,
    DeploymentAssets,
)
from infra.guardrails import validate_cloudformation  # noqa: E402


EXPECTED_RESOURCE_TYPES = {
    "AWS::Amplify::App",
    "AWS::Amplify::Branch",
    "AWS::ApiGatewayV2::Api",
    "AWS::Bedrock::DataSource",
    "AWS::Bedrock::KnowledgeBase",
    "AWS::BedrockAgentCore::Gateway",
    "AWS::BedrockAgentCore::GatewayTarget",
    "AWS::BedrockAgentCore::Runtime",
    "AWS::BedrockAgentCore::RuntimeEndpoint",
    "AWS::Cognito::UserPool",
    "AWS::Cognito::UserPoolClient",
    "AWS::Cognito::UserPoolGroup",
    "AWS::EC2::Subnet",
    "AWS::EC2::VPC",
    "AWS::EC2::VPCEndpoint",
    "AWS::KMS::Key",
    "AWS::Lambda::Function",
    "AWS::RDS::DBInstance",
    "AWS::S3::Bucket",
    "AWS::S3Vectors::Index",
    "AWS::S3Vectors::VectorBucket",
    "AWS::SecretsManager::Secret",
    "AWS::StepFunctions::StateMachine",
}


class AiwaveStagingStackTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._temporary_directory = tempfile.TemporaryDirectory()
        root = Path(cls._temporary_directory.name)
        api_code = root / "api"
        runtime_code = root / "runtime"
        api_code.mkdir()
        runtime_code.mkdir()
        (api_code / "lambda_handler.py").write_text(
            "def handler(event, context): return {'statusCode': 200}\n",
            encoding="utf-8",
        )
        (runtime_code / "agent_runtime.py").write_text(
            "print('fixture')\n",
            encoding="utf-8",
        )

        app = App()
        stack = AiwaveStagingStack(
            app,
            "AiwaveStaging",
            env=Environment(account="123456789012", region="us-west-2"),
            assets=DeploymentAssets(
                api_code=api_code,
                agent_runtime_code=runtime_code,
                bundle=False,
            ),
        )
        cls.template = Template.from_stack(stack).to_json()

    @classmethod
    def tearDownClass(cls) -> None:
        cls._temporary_directory.cleanup()

    def resources(self, resource_type: str) -> list[dict[str, Any]]:
        return [
            resource
            for resource in self.template["Resources"].values()
            if resource["Type"] == resource_type
        ]

    def test_declares_the_formal_aws_only_service_set(self) -> None:
        actual_types = {
            resource["Type"] for resource in self.template["Resources"].values()
        }

        self.assertTrue(EXPECTED_RESOURCE_TYPES.issubset(actual_types))
        self.assertFalse(any("Supabase" in value for value in actual_types))

    def test_network_has_two_isolated_azs_and_no_public_compute_path(self) -> None:
        self.assertEqual(len(self.resources("AWS::EC2::Subnet")), 2)
        self.assertEqual(self.resources("AWS::EC2::NatGateway"), [])
        self.assertEqual(self.resources("AWS::EC2::InternetGateway"), [])
        self.assertEqual(self.resources("AWS::EC2::Instance"), [])

        for subnet in self.resources("AWS::EC2::Subnet"):
            self.assertFalse(subnet["Properties"]["MapPublicIpOnLaunch"])
        availability_zones = json.dumps(
            [
                subnet["Properties"]["AvailabilityZone"]
                for subnet in self.resources("AWS::EC2::Subnet")
            ]
        )
        self.assertNotIn("dummy", availability_zones)
        self.assertIn("Fn::GetAZs", availability_zones)

        security_groups = self.resources("AWS::EC2::SecurityGroup")
        for security_group in security_groups:
            for ingress in security_group["Properties"].get(
                "SecurityGroupIngress",
                [],
            ):
                self.assertNotIn("CidrIp", ingress)
                self.assertNotIn("CidrIpv6", ingress)

    def test_storage_and_database_are_private_and_cost_bounded(self) -> None:
        buckets = self.resources("AWS::S3::Bucket")
        self.assertEqual(len(buckets), 2)
        for bucket in buckets:
            public_access = bucket["Properties"][
                "PublicAccessBlockConfiguration"
            ]
            self.assertEqual(
                public_access,
                {
                    "BlockPublicAcls": True,
                    "BlockPublicPolicy": True,
                    "IgnorePublicAcls": True,
                    "RestrictPublicBuckets": True,
                },
            )
            self.assertIn("BucketEncryption", bucket["Properties"])

        databases = self.resources("AWS::RDS::DBInstance")
        self.assertEqual(len(databases), 1)
        database = databases[0]["Properties"]
        self.assertFalse(database["PubliclyAccessible"])
        self.assertFalse(database["MultiAZ"])
        self.assertTrue(database["StorageEncrypted"])
        self.assertEqual(database["DBInstanceClass"], "db.t4g.micro")
        self.assertEqual(database["EngineVersion"], "16.13")
        self.assertEqual(database["BackupRetentionPeriod"], 0)

        self.assertEqual(self.resources("AWS::OpenSearchServerless::Collection"), [])
        self.assertEqual(self.resources("AWS::EMR::Cluster"), [])
        self.assertEqual(self.resources("AWS::SageMaker::TrainingJob"), [])

    def test_lambda_architecture_matches_arm64_native_bundle(self) -> None:
        functions = self.resources("AWS::Lambda::Function")
        self.assertEqual(len(functions), 2)
        for function in functions:
            self.assertEqual(
                function["Properties"].get("Architectures"),
                ["arm64"],
            )

    def test_flask_lambda_can_invoke_only_runtime_and_staging_endpoint(self) -> None:
        invoke_statements = []
        for policy in self.resources("AWS::IAM::Policy"):
            for statement in policy["Properties"]["PolicyDocument"]["Statement"]:
                actions = statement["Action"]
                if not isinstance(actions, list):
                    actions = [actions]
                if "bedrock-agentcore:InvokeAgentRuntime" in actions:
                    invoke_statements.append(statement)

        self.assertEqual(len(invoke_statements), 1)
        resources = invoke_statements[0]["Resource"]
        self.assertIsInstance(resources, list)
        self.assertEqual(len(resources), 2)
        serialized = json.dumps(resources)
        self.assertIn("AgentRuntimeArn", serialized)
        self.assertIn("AgentRuntimeEndpointArn", serialized)

    def test_one_runtime_hosts_the_supervisor_and_five_logical_agents(self) -> None:
        runtimes = self.resources("AWS::BedrockAgentCore::Runtime")
        self.assertEqual(len(runtimes), 1)
        code_configuration = runtimes[0]["Properties"]["AgentRuntimeArtifact"][
            "CodeConfiguration"
        ]
        self.assertEqual(code_configuration["EntryPoint"], ["agent_runtime.py"])
        runtime_environment = runtimes[0]["Properties"]["EnvironmentVariables"]
        self.assertEqual(
            runtime_environment["LOGICAL_AGENTS"],
            (
                "restaurant_agent,product_agent,housekeeping_agent,"
                "utility_repair_agent,community_service_agent"
            ),
        )
        self.assertEqual(
            runtime_environment["BEDROCK_MODEL_ID"],
            "amazon.nova-2-lite-v1:0",
        )
        self.assertEqual(len(self.resources("AWS::BedrockAgentCore::Gateway")), 1)
        self.assertEqual(
            len(self.resources("AWS::BedrockAgentCore::GatewayTarget")),
            1,
        )

    def test_gateway_role_has_creation_time_kms_and_lambda_permissions(self) -> None:
        gateway = self.resources("AWS::BedrockAgentCore::Gateway")[0]
        role_logical_id = gateway["Properties"]["RoleArn"]["Fn::GetAtt"][0]
        role = self.template["Resources"][role_logical_id]
        inline_policies = role["Properties"].get("Policies", [])
        actions = {
            action
            for policy in inline_policies
            for statement in policy["PolicyDocument"]["Statement"]
            for action in (
                statement["Action"]
                if isinstance(statement["Action"], list)
                else [statement["Action"]]
            )
        }

        self.assertIn("kms:GenerateDataKey*", actions)
        self.assertIn("lambda:InvokeFunction", actions)

    def test_managed_knowledge_base_uses_titan_and_s3_vectors(self) -> None:
        vector_buckets = self.resources("AWS::S3Vectors::VectorBucket")
        self.assertEqual(len(vector_buckets), 1)
        self.assertEqual(
            vector_buckets[0]["Properties"]["EncryptionConfiguration"],
            {"SseType": "AES256"},
        )
        indexes = self.resources("AWS::S3Vectors::Index")
        self.assertEqual(len(indexes), 1)
        self.assertEqual(indexes[0]["Properties"]["Dimension"], 1024)
        self.assertEqual(indexes[0]["Properties"]["DistanceMetric"], "cosine")
        self.assertEqual(
            indexes[0]["Properties"]
            .get("MetadataConfiguration", {})
            .get("NonFilterableMetadataKeys"),
            ["AMAZON_BEDROCK_TEXT", "AMAZON_BEDROCK_METADATA"],
        )

        serialized = json.dumps(self.template)
        self.assertIn("amazon.titan-embed-text-v2:0", serialized)
        self.assertIn("amazon.nova-2-lite-v1:0", serialized)
        self.assertNotIn("cohere.", serialized)
        self.assertNotIn("anthropic.", serialized)

    def test_cognito_defines_all_demo_roles(self) -> None:
        groups = {
            group["Properties"]["GroupName"]
            for group in self.resources("AWS::Cognito::UserPoolGroup")
        }
        self.assertEqual(groups, {"RESIDENT", "PROVIDER", "ADMIN"})

    def test_synthesized_template_passes_hackathon_guardrails(self) -> None:
        validate_cloudformation(self.template)

    def test_outputs_support_post_deploy_smoke_and_frontend_publish(self) -> None:
        self.assertTrue(
            {
                "ApiBaseUrl",
                "AmplifyAppId",
                "AmplifyBranchName",
                "FrontendUrl",
                "KnowledgeBaseBucketName",
                "KnowledgeBaseId",
                "KnowledgeBaseDataSourceId",
                "AgentRuntimeArn",
                "AgentRuntimeEndpointArn",
                "AgentGatewayUrl",
                "UserPoolId",
                "UserPoolClientId",
            }.issubset(self.template["Outputs"])
        )


if __name__ == "__main__":
    unittest.main()
