"""Cost-bounded AWS staging stack for the hackathon walking skeleton.

The stack intentionally keeps resident-facing HTTP public while all stateful
resources and compute-to-service traffic stay on isolated subnets.  It creates
one AgentCore Runtime that hosts the Supervisor and five logical agents.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from aws_cdk import (
    BundlingOptions,
    CfnOutput,
    Duration,
    Fn,
    RemovalPolicy,
    Stack,
    aws_amplify as amplify,
    aws_apigatewayv2 as apigwv2,
    aws_apigatewayv2_integrations as apigwv2_integrations,
    aws_bedrock as bedrock,
    aws_bedrockagentcore as agentcore,
    aws_cognito as cognito,
    aws_ec2 as ec2,
    aws_iam as iam,
    aws_kms as kms,
    aws_lambda as lambda_,
    aws_rds as rds,
    aws_s3 as s3,
    aws_s3vectors as s3vectors,
    aws_stepfunctions as sfn,
)
from constructs import Construct


NOVA_MODEL_ID = "amazon.nova-2-lite-v1:0"
TITAN_EMBEDDING_MODEL_ID = "amazon.titan-embed-text-v2:0"
LOGICAL_AGENTS = (
    "restaurant_agent,product_agent,housekeeping_agent,"
    "utility_repair_agent,community_service_agent"
)


@dataclass(frozen=True)
class DeploymentAssets:
    """Local source roots used to build the Lambda and AgentCore artifacts."""

    api_code: Path
    agent_runtime_code: Path
    bundle: bool = True

    @classmethod
    def from_repository(cls) -> "DeploymentAssets":
        repository_root = Path(__file__).resolve().parents[1]
        return cls(
            api_code=repository_root / "packages" / "api",
            agent_runtime_code=repository_root / "infra" / "runtime",
        )


class AiwaveStagingStack(Stack):
    """Formal AWS-only staging architecture for the demo."""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        assets: DeploymentAssets | None = None,
        **kwargs: object,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)
        if self.region != "us-west-2":
            raise ValueError("AiwaveStagingStack is restricted to AWS region us-west-2")
        deployment_assets = assets or DeploymentAssets.from_repository()

        encryption_key = kms.Key(
            self,
            "ApplicationKey",
            alias="alias/aiwave-staging",
            enable_key_rotation=True,
            removal_policy=RemovalPolicy.DESTROY,
        )

        vpc, workload_security_group = self._create_private_network()

        knowledge_base_bucket = self._private_bucket(
            "KnowledgeBaseSourceBucket",
            encryption_key,
        )
        artifact_bucket = self._private_bucket(
            "ResidentArtifactBucket",
            encryption_key,
        )

        database = self._create_database(
            vpc=vpc,
            workload_security_group=workload_security_group,
            encryption_key=encryption_key,
        )

        user_pool, user_pool_client = self._create_identity()
        workflow = self._create_workflow()
        api_function, tool_function = self._create_lambda_functions(
            assets=deployment_assets,
            vpc=vpc,
            workload_security_group=workload_security_group,
            database=database,
            artifact_bucket=artifact_bucket,
            workflow=workflow,
        )
        http_api = self._create_http_api(api_function)

        knowledge_base, data_source = self._create_knowledge_base(
            source_bucket=knowledge_base_bucket,
            encryption_key=encryption_key,
        )
        gateway = self._create_gateway(
            tool_function=tool_function,
            encryption_key=encryption_key,
        )
        runtime, runtime_endpoint = self._create_agent_runtime(
            assets=deployment_assets,
            vpc=vpc,
            workload_security_group=workload_security_group,
            gateway=gateway,
            knowledge_base=knowledge_base,
        )
        api_function.add_environment("ORCHESTRATION_MODE", "agentcore-runtime")
        api_function.add_environment(
            "AGENT_RUNTIME_ARN",
            runtime.agent_runtime_arn,
        )
        api_function.add_environment("AGENT_RUNTIME_QUALIFIER", "staging")
        api_function.add_to_role_policy(
            iam.PolicyStatement(
                actions=["bedrock-agentcore:InvokeAgentRuntime"],
                resources=[runtime.agent_runtime_arn],
            )
        )

        amplify_app, amplify_branch = self._create_frontend()
        self._create_outputs(
            http_api=http_api,
            amplify_app=amplify_app,
            amplify_branch=amplify_branch,
            knowledge_base_bucket=knowledge_base_bucket,
            knowledge_base=knowledge_base,
            data_source=data_source,
            runtime=runtime,
            runtime_endpoint=runtime_endpoint,
            gateway=gateway,
            user_pool=user_pool,
            user_pool_client=user_pool_client,
        )

    def _create_private_network(
        self,
    ) -> tuple[ec2.Vpc, ec2.SecurityGroup]:
        vpc = ec2.Vpc(
            self,
            "Vpc",
            ip_addresses=ec2.IpAddresses.cidr("10.42.0.0/16"),
            availability_zones=[
                Fn.select(0, Fn.get_azs("us-west-2")),
                Fn.select(1, Fn.get_azs("us-west-2")),
            ],
            nat_gateways=0,
            subnet_configuration=[
                ec2.SubnetConfiguration(
                    name="application",
                    subnet_type=ec2.SubnetType.PRIVATE_ISOLATED,
                    cidr_mask=24,
                )
            ],
        )

        workload_security_group = ec2.SecurityGroup(
            self,
            "WorkloadSecurityGroup",
            vpc=vpc,
            description="Egress identity for Lambda and AgentCore workloads",
            allow_all_outbound=True,
        )
        endpoint_security_group = ec2.SecurityGroup(
            self,
            "EndpointSecurityGroup",
            vpc=vpc,
            description="Only application workloads may call private endpoints",
            allow_all_outbound=False,
        )
        endpoint_security_group.add_ingress_rule(
            workload_security_group,
            ec2.Port.tcp(443),
            "HTTPS from application workloads",
        )

        vpc.add_gateway_endpoint(
            "S3Endpoint",
            service=ec2.GatewayVpcEndpointAwsService.S3,
            subnets=[
                ec2.SubnetSelection(
                    subnet_type=ec2.SubnetType.PRIVATE_ISOLATED,
                )
            ],
        )
        endpoint_services = {
            "AgentCoreControlEndpoint": (
                ec2.InterfaceVpcEndpointAwsService.BEDROCK_AGENTCORE
            ),
            "AgentCoreGatewayEndpoint": (
                ec2.InterfaceVpcEndpointAwsService.BEDROCK_AGENTCORE_GATEWAY
            ),
            "AgentCoreRuntimeEndpoint": (
                ec2.InterfaceVpcEndpointAwsService.BEDROCK_AGENT_RUNTIME
            ),
            "BedrockRuntimeEndpoint": (
                ec2.InterfaceVpcEndpointAwsService.BEDROCK_RUNTIME
            ),
            "SecretsManagerEndpoint": (
                ec2.InterfaceVpcEndpointAwsService.SECRETS_MANAGER
            ),
            "StepFunctionsEndpoint": (
                ec2.InterfaceVpcEndpointAwsService.STEP_FUNCTIONS
            ),
        }
        for endpoint_id, service in endpoint_services.items():
            vpc.add_interface_endpoint(
                endpoint_id,
                service=service,
                open=False,
                private_dns_enabled=True,
                security_groups=[endpoint_security_group],
                subnets=ec2.SubnetSelection(
                    subnet_type=ec2.SubnetType.PRIVATE_ISOLATED,
                ),
            )

        return vpc, workload_security_group

    def _private_bucket(self, construct_id: str, key: kms.IKey) -> s3.Bucket:
        return s3.Bucket(
            self,
            construct_id,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            encryption=s3.BucketEncryption.KMS,
            encryption_key=key,
            enforce_ssl=True,
            versioned=True,
            removal_policy=RemovalPolicy.DESTROY,
        )

    def _create_database(
        self,
        *,
        vpc: ec2.IVpc,
        workload_security_group: ec2.ISecurityGroup,
        encryption_key: kms.IKey,
    ) -> rds.DatabaseInstance:
        database_security_group = ec2.SecurityGroup(
            self,
            "DatabaseSecurityGroup",
            vpc=vpc,
            description="PostgreSQL only from application workloads",
            allow_all_outbound=False,
        )
        database_security_group.add_ingress_rule(
            workload_security_group,
            ec2.Port.tcp(5432),
            "PostgreSQL from application workloads",
        )

        return rds.DatabaseInstance(
            self,
            "Database",
            engine=rds.DatabaseInstanceEngine.postgres(
                version=rds.PostgresEngineVersion.VER_16_13,
            ),
            instance_type=ec2.InstanceType.of(
                ec2.InstanceClass.BURSTABLE4_GRAVITON,
                ec2.InstanceSize.MICRO,
            ),
            credentials=rds.Credentials.from_generated_secret(
                "aiwave_app",
                encryption_key=encryption_key,
            ),
            database_name="aiwave",
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(
                subnet_type=ec2.SubnetType.PRIVATE_ISOLATED,
            ),
            security_groups=[database_security_group],
            publicly_accessible=False,
            multi_az=False,
            allocated_storage=20,
            max_allocated_storage=20,
            storage_encrypted=True,
            storage_encryption_key=encryption_key,
            backup_retention=Duration.days(0),
            deletion_protection=False,
            delete_automated_backups=True,
            removal_policy=RemovalPolicy.DESTROY,
        )

    def _create_identity(
        self,
    ) -> tuple[cognito.UserPool, cognito.UserPoolClient]:
        user_pool = cognito.UserPool(
            self,
            "UserPool",
            user_pool_name="aiwave-staging-users",
            self_sign_up_enabled=False,
            sign_in_aliases=cognito.SignInAliases(email=True),
            account_recovery=cognito.AccountRecovery.NONE,
            removal_policy=RemovalPolicy.DESTROY,
        )
        client = user_pool.add_client(
            "WebClient",
            user_pool_client_name="aiwave-staging-web",
            auth_flows=cognito.AuthFlow(user_srp=True),
            generate_secret=False,
            prevent_user_existence_errors=True,
        )
        for group_name, precedence in (
            ("ADMIN", 1),
            ("PROVIDER", 2),
            ("RESIDENT", 3),
        ):
            cognito.CfnUserPoolGroup(
                self,
                f"{group_name.title()}Group",
                group_name=group_name,
                precedence=precedence,
                user_pool_id=user_pool.user_pool_id,
            )
        return user_pool, client

    def _create_workflow(self) -> sfn.StateMachine:
        definition = sfn.Chain.start(
            sfn.Pass(
                self,
                "RecordRequest",
                comment="Persist service_request before provider dispatch",
            )
        ).next(
            sfn.Succeed(
                self,
                "AwaitProviderEvents",
                comment=(
                    "Provider events are demo-driven through the API; the state "
                    "machine remains the durable orchestration boundary"
                ),
            )
        )
        return sfn.StateMachine(
            self,
            "ServiceRequestWorkflow",
            definition_body=sfn.DefinitionBody.from_chainable(definition),
            state_machine_type=sfn.StateMachineType.STANDARD,
            removal_policy=RemovalPolicy.DESTROY,
        )

    def _lambda_code(
        self,
        assets: DeploymentAssets,
    ) -> lambda_.Code:
        if not assets.bundle:
            return lambda_.Code.from_asset(str(assets.api_code))
        return lambda_.Code.from_asset(
            str(assets.api_code),
            bundling=BundlingOptions(
                image=lambda_.Runtime.PYTHON_3_12.bundling_image,
                command=[
                    "bash",
                    "-c",
                    (
                        "pip install -r requirements.txt -t /asset-output "
                        "&& cp -au . /asset-output"
                    ),
                ],
            ),
        )

    def _create_lambda_functions(
        self,
        *,
        assets: DeploymentAssets,
        vpc: ec2.IVpc,
        workload_security_group: ec2.ISecurityGroup,
        database: rds.DatabaseInstance,
        artifact_bucket: s3.IBucket,
        workflow: sfn.IStateMachine,
    ) -> tuple[lambda_.Function, lambda_.Function]:
        code = self._lambda_code(assets)
        common_environment = {
            "APP_ENV": "staging",
            "STORE_BACKEND": "rds",
            "DATABASE_SECRET_ARN": database.secret.secret_arn,
            "DATABASE_HOST": database.db_instance_endpoint_address,
            "DATABASE_NAME": "aiwave",
            "ARTIFACT_BUCKET_NAME": artifact_bucket.bucket_name,
            "SERVICE_REQUEST_STATE_MACHINE_ARN": workflow.state_machine_arn,
            "BEDROCK_MODEL_ID": NOVA_MODEL_ID,
        }
        function_kwargs = {
            "runtime": lambda_.Runtime.PYTHON_3_12,
            "architecture": lambda_.Architecture.ARM_64,
            "code": code,
            "timeout": Duration.seconds(29),
            "memory_size": 512,
            "vpc": vpc,
            "vpc_subnets": ec2.SubnetSelection(
                subnet_type=ec2.SubnetType.PRIVATE_ISOLATED,
            ),
            "security_groups": [workload_security_group],
            "environment": common_environment,
        }
        api_function = lambda_.Function(
            self,
            "FlaskApiFunction",
            handler="lambda_handler.handler",
            description="Flask HTTP API adapter",
            **function_kwargs,
        )
        tool_function = lambda_.Function(
            self,
            "UtilityToolFunction",
            handler="tool_lambda.handler",
            description="AgentCore Gateway utility repair tools",
            **function_kwargs,
        )

        for function in (api_function, tool_function):
            database.secret.grant_read(function)
            artifact_bucket.grant_read_write(function)
            workflow.grant_start_execution(function)
        return api_function, tool_function

    def _create_http_api(
        self,
        api_function: lambda_.IFunction,
    ) -> apigwv2.HttpApi:
        return apigwv2.HttpApi(
            self,
            "HttpApi",
            api_name="aiwave-staging-api",
            default_integration=apigwv2_integrations.HttpLambdaIntegration(
                "FlaskIntegration",
                api_function,
                payload_format_version=apigwv2.PayloadFormatVersion.VERSION_2_0,
            ),
            cors_preflight=apigwv2.CorsPreflightOptions(
                allow_headers=["authorization", "content-type", "x-demo-role"],
                allow_methods=[apigwv2.CorsHttpMethod.ANY],
                allow_origins=["http://localhost:5173"],
                max_age=Duration.hours(1),
            ),
        )

    def _create_knowledge_base(
        self,
        *,
        source_bucket: s3.IBucket,
        encryption_key: kms.IKey,
    ) -> tuple[bedrock.CfnKnowledgeBase, bedrock.CfnDataSource]:
        vector_bucket = s3vectors.CfnVectorBucket(
            self,
            "KnowledgeVectorBucket",
            vector_bucket_name="aiwave-utility-repair-vectors",
            encryption_configuration=(
                s3vectors.CfnVectorBucket.EncryptionConfigurationProperty(
                    sse_type="AES256",
                )
            ),
        )
        vector_bucket.apply_removal_policy(RemovalPolicy.DESTROY)
        vector_index = s3vectors.CfnIndex(
            self,
            "KnowledgeVectorIndex",
            index_name="utility-repair",
            vector_bucket_arn=vector_bucket.attr_vector_bucket_arn,
            data_type="float32",
            dimension=1024,
            distance_metric="cosine",
        )
        vector_index.apply_removal_policy(RemovalPolicy.DESTROY)
        vector_index.add_resource_dependency(vector_bucket)

        role = iam.Role(
            self,
            "KnowledgeBaseRole",
            assumed_by=iam.ServicePrincipal("bedrock.amazonaws.com"),
            description="Least-privilege Bedrock knowledge base ingestion role",
        )
        source_bucket.grant_read(role)
        encryption_key.grant_encrypt_decrypt(role)
        role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "s3vectors:GetVectorBucket",
                    "s3vectors:GetIndex",
                    "s3vectors:PutVectors",
                    "s3vectors:GetVectors",
                    "s3vectors:QueryVectors",
                    "s3vectors:DeleteVectors",
                ],
                resources=[
                    vector_bucket.attr_vector_bucket_arn,
                    vector_index.attr_index_arn,
                ],
            )
        )
        role.add_to_policy(
            iam.PolicyStatement(
                actions=["bedrock:InvokeModel"],
                resources=[self._model_arn(TITAN_EMBEDDING_MODEL_ID)],
            )
        )

        knowledge_base = bedrock.CfnKnowledgeBase(
            self,
            "KnowledgeBase",
            name="aiwave-utility-repair",
            role_arn=role.role_arn,
            knowledge_base_configuration=(
                bedrock.CfnKnowledgeBase.KnowledgeBaseConfigurationProperty(
                    type="VECTOR",
                    vector_knowledge_base_configuration=(
                        bedrock.CfnKnowledgeBase.VectorKnowledgeBaseConfigurationProperty(
                            embedding_model_arn=self._model_arn(
                                TITAN_EMBEDDING_MODEL_ID
                            ),
                            embedding_model_configuration=(
                                bedrock.CfnKnowledgeBase.EmbeddingModelConfigurationProperty(
                                    bedrock_embedding_model_configuration=(
                                        bedrock.CfnKnowledgeBase.BedrockEmbeddingModelConfigurationProperty(
                                            dimensions=1024,
                                            embedding_data_type="FLOAT32",
                                        )
                                    )
                                )
                            ),
                        )
                    ),
                )
            ),
            storage_configuration=(
                bedrock.CfnKnowledgeBase.StorageConfigurationProperty(
                    type="S3_VECTORS",
                    s3_vectors_configuration=(
                        bedrock.CfnKnowledgeBase.S3VectorsConfigurationProperty(
                            index_arn=vector_index.attr_index_arn,
                        )
                    ),
                )
            ),
        )
        knowledge_base.add_resource_dependency(vector_index)
        knowledge_base.node.add_dependency(role)

        data_source = bedrock.CfnDataSource(
            self,
            "KnowledgeBaseDataSource",
            name="aiwave-utility-repair-s3",
            knowledge_base_id=knowledge_base.attr_knowledge_base_id,
            data_source_configuration=(
                bedrock.CfnDataSource.DataSourceConfigurationProperty(
                    type="S3",
                    s3_configuration=(
                        bedrock.CfnDataSource.S3DataSourceConfigurationProperty(
                            bucket_arn=source_bucket.bucket_arn,
                            inclusion_prefixes=["utility_repair/"],
                        )
                    ),
                )
            ),
            vector_ingestion_configuration=(
                bedrock.CfnDataSource.VectorIngestionConfigurationProperty(
                    chunking_configuration=(
                        bedrock.CfnDataSource.ChunkingConfigurationProperty(
                            chunking_strategy="FIXED_SIZE",
                            fixed_size_chunking_configuration=(
                                bedrock.CfnDataSource.FixedSizeChunkingConfigurationProperty(
                                    max_tokens=500,
                                    overlap_percentage=20,
                                )
                            ),
                        )
                    )
                )
            ),
        )
        data_source.add_resource_dependency(knowledge_base)
        return knowledge_base, data_source

    def _create_gateway(
        self,
        *,
        tool_function: lambda_.IFunction,
        encryption_key: kms.IKey,
    ) -> agentcore.Gateway:
        gateway_role = iam.Role(
            self,
            "AgentGatewayRole",
            assumed_by=iam.ServicePrincipal("bedrock-agentcore.amazonaws.com"),
            description="Least-privilege AgentCore Gateway service role",
            inline_policies={
                "GatewayCreationPermissions": iam.PolicyDocument(
                    statements=[
                        iam.PolicyStatement(
                            actions=[
                                "kms:Decrypt",
                                "kms:Encrypt",
                                "kms:ReEncrypt*",
                                "kms:GenerateDataKey*",
                                "kms:DescribeKey",
                            ],
                            resources=[encryption_key.key_arn],
                        ),
                        iam.PolicyStatement(
                            actions=["lambda:InvokeFunction"],
                            resources=[
                                tool_function.function_arn,
                                f"{tool_function.function_arn}:*",
                            ],
                        ),
                    ]
                )
            },
        )
        gateway = agentcore.Gateway(
            self,
            "AgentGateway",
            gateway_name="aiwave-staging-tools",
            description="Private IAM-authorized tools for the logical agents",
            authorizer_configuration=agentcore.GatewayAuthorizer.using_aws_iam(),
            kms_key=encryption_key,
            role=gateway_role,
        )
        gateway.add_lambda_target(
            "UtilityRepairTarget",
            gateway_target_name="utility-repair-tools",
            description="Create, update, match and inspect utility repair requests",
            lambda_function=tool_function,
            tool_schema=agentcore.ToolSchema.from_inline(
                [
                    agentcore.ToolDefinition(
                        name="utility_service_request",
                        description=(
                            "Create or update the water and electricity repair "
                            "service request and provider workflow"
                        ),
                        input_schema=agentcore.SchemaDefinition(
                            type=agentcore.SchemaDefinitionType.OBJECT,
                            properties={
                                "operation": agentcore.SchemaDefinition(
                                    type=agentcore.SchemaDefinitionType.STRING,
                                    description="Requested workflow operation",
                                ),
                                "request_id": agentcore.SchemaDefinition(
                                    type=agentcore.SchemaDefinitionType.STRING,
                                    description="Existing request id when applicable",
                                ),
                                "payload": agentcore.SchemaDefinition(
                                    type=agentcore.SchemaDefinitionType.OBJECT,
                                    description="Operation-specific structured values",
                                ),
                            },
                            required=["operation"],
                        ),
                    )
                ]
            ),
        )
        return gateway

    def _agent_artifact(
        self,
        assets: DeploymentAssets,
    ) -> agentcore.AgentRuntimeArtifact:
        bundling = None
        if assets.bundle:
            bundling = BundlingOptions(
                image=lambda_.Runtime.PYTHON_3_12.bundling_image,
                command=[
                    "bash",
                    "-c",
                    (
                        "pip install -r requirements.txt -t /asset-output "
                        "&& cp -au . /asset-output"
                    ),
                ],
            )
        return agentcore.AgentRuntimeArtifact.from_code_asset(
            path=str(assets.agent_runtime_code),
            runtime=agentcore.AgentCoreRuntime.PYTHON_3_12,
            entrypoint=["agent_runtime.py"],
            bundling=bundling,
        )

    def _create_agent_runtime(
        self,
        *,
        assets: DeploymentAssets,
        vpc: ec2.IVpc,
        workload_security_group: ec2.ISecurityGroup,
        gateway: agentcore.IGateway,
        knowledge_base: bedrock.CfnKnowledgeBase,
    ) -> tuple[agentcore.Runtime, agentcore.RuntimeEndpoint]:
        execution_role = iam.Role(
            self,
            "AgentRuntimeRole",
            assumed_by=iam.ServicePrincipal("bedrock-agentcore.amazonaws.com"),
            description="One runtime for Supervisor and five logical agents",
        )
        execution_role.add_to_policy(
            iam.PolicyStatement(
                actions=["bedrock:InvokeModel"],
                resources=[self._model_arn(NOVA_MODEL_ID)],
            )
        )
        execution_role.add_to_policy(
            iam.PolicyStatement(
                actions=["bedrock:Retrieve"],
                resources=[knowledge_base.attr_knowledge_base_arn],
            )
        )
        gateway.grant_invoke(execution_role)

        runtime = agentcore.Runtime(
            self,
            "AgentRuntime",
            runtime_name="aiwave_staging_supervisor",
            description="Supervisor plus five in-process logical domain agents",
            agent_runtime_artifact=self._agent_artifact(assets),
            execution_role=execution_role,
            network_configuration=agentcore.RuntimeNetworkConfiguration.using_vpc(
                self,
                vpc=vpc,
                security_groups=[workload_security_group],
                vpc_subnets=ec2.SubnetSelection(
                    subnet_type=ec2.SubnetType.PRIVATE_ISOLATED,
                ),
            ),
            environment_variables={
                "APP_ENV": "staging",
                "BEDROCK_MODEL_ID": NOVA_MODEL_ID,
                "BEDROCK_MIN_REQUEST_INTERVAL_SECONDS": "1.05",
                "LOGICAL_AGENTS": LOGICAL_AGENTS,
                "KNOWLEDGE_BASE_ID": knowledge_base.attr_knowledge_base_id,
                "AGENT_GATEWAY_URL": gateway.gateway_url or "",
            },
        )
        runtime.node.add_dependency(knowledge_base)
        endpoint = runtime.add_endpoint(
            "staging",
            description="Stable staging endpoint used by the Flask API",
        )
        return runtime, endpoint

    def _create_frontend(
        self,
    ) -> tuple[amplify.CfnApp, amplify.CfnBranch]:
        app = amplify.CfnApp(
            self,
            "FrontendApp",
            name="aiwave-staging-web",
            description="Manual artifact deployment for the hackathon frontend",
            custom_rules=[
                amplify.CfnApp.CustomRuleProperty(
                    source="</^[^.]+$|\\.(?!(css|gif|ico|jpg|js|png|txt|svg|woff|woff2)$)([^.]+$)/>",
                    target="/index.html",
                    status="200",
                )
            ],
        )
        branch = amplify.CfnBranch(
            self,
            "FrontendBranch",
            app_id=app.attr_app_id,
            branch_name="staging",
            enable_auto_build=False,
            stage="DEVELOPMENT",
        )
        branch.add_resource_dependency(app)
        return app, branch

    def _model_arn(self, model_id: str) -> str:
        # The staging architecture is deliberately region-locked above.  A
        # literal ARN lets the fail-closed guardrail audit the exact allowlist
        # without trusting unresolved CloudFormation string functions.
        return f"arn:aws:bedrock:us-west-2::foundation-model/{model_id}"

    def _create_outputs(
        self,
        *,
        http_api: apigwv2.HttpApi,
        amplify_app: amplify.CfnApp,
        amplify_branch: amplify.CfnBranch,
        knowledge_base_bucket: s3.IBucket,
        knowledge_base: bedrock.CfnKnowledgeBase,
        data_source: bedrock.CfnDataSource,
        runtime: agentcore.Runtime,
        runtime_endpoint: agentcore.RuntimeEndpoint,
        gateway: agentcore.IGateway,
        user_pool: cognito.IUserPool,
        user_pool_client: cognito.IUserPoolClient,
    ) -> None:
        outputs = {
            "ApiBaseUrl": http_api.api_endpoint,
            "AmplifyAppId": amplify_app.attr_app_id,
            "AmplifyBranchName": amplify_branch.branch_name,
            "FrontendUrl": (
                f"https://{amplify_branch.branch_name}."
                f"{amplify_app.attr_default_domain}"
            ),
            "KnowledgeBaseBucketName": knowledge_base_bucket.bucket_name,
            "KnowledgeBaseId": knowledge_base.attr_knowledge_base_id,
            "KnowledgeBaseDataSourceId": data_source.attr_data_source_id,
            "AgentRuntimeArn": runtime.agent_runtime_arn,
            "AgentRuntimeEndpointArn": (
                runtime_endpoint.agent_runtime_endpoint_arn
            ),
            "AgentGatewayUrl": gateway.gateway_url or "",
            "UserPoolId": user_pool.user_pool_id,
            "UserPoolClientId": user_pool_client.user_pool_client_id,
        }
        for logical_id, value in outputs.items():
            CfnOutput(self, logical_id, value=value)
