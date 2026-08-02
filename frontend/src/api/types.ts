export type WorkflowStage =
  | "collecting_details"
  | "safety_hold"
  | "awaiting_resident_confirmation"
  | "waiting_provider_response"
  | "waiting_resident_information"
  | "rematching"
  | "provider_confirmed"
  | "awaiting_resident_acceptance"
  | "completed";

export interface ApiMessage {
  messageId: string;
  conversationId: string;
  role: "user" | "assistant";
  content: string;
  agent: string | null;
  kind: "message" | "final";
  createdAt: string;
}

export interface ProviderSummary {
  providerId: string;
  name: string;
  rating?: number;
  responseSlaHours?: number;
  capabilities?: string[];
}

export interface ProgressEvent {
  eventType: string;
  label: string;
  at: string;
}

/** 對應 mms_order_record.point_status：01 待發放 / 02 已發放 / 03 不發放 / 04 已取消 */
export type PointStatus = "01" | "02" | "03" | "04";

export interface PointsReward {
  program: "OPENPOINT";
  status: PointStatus;
  statusLabel: string;
  /** 訂單成立時揭露的預估點數，發放後仍保留供比較。 */
  estimatedPoints: number;
  /** 住戶驗收發放後才有值；未發放為 null。 */
  grantedPoints: number | null;
  earnRate: string;
  earnRateBasisPoints: number;
  /** 目前的計算基礎；發放後等於完工金額。 */
  basisAmount: number;
  estimatedBasisAmount: number;
  amountSource: "provider_reported" | "issue_type_baseline";
  amountSourceLabel: string;
  capped: boolean;
  maxPointsPerOrder: number;
  /** 完工金額使實際點數與預估不同時為 true。 */
  amountAdjusted: boolean;
  grantCondition: string;
  isDemoLedger: boolean;
  disclosure: string;
  estimatedAt: string;
  grantedAt: string | null;
}

export interface ProviderActiveCase {
  serviceRequestId: string;
  stage: WorkflowStage;
  displayLabel: string;
  summary: string;
  arrivalWindow: string | null;
  estimatedAmount: number | null;
  canReportCompletion: boolean;
  updatedAt: string;
}

export interface ProviderCompletionRequest {
  message?: string;
  /** 完工實付金額（新台幣元）；未填則沿用訂單成立時的計算基礎。 */
  finalAmount?: number;
}

export interface WorkflowProgress {
  serviceRequestId: string;
  stage: WorkflowStage;
  waitingFor: "resident" | "provider" | "admin" | null;
  displayLabel: string;
  residentActionRequired: boolean;
  latestEventAt: string;
  events?: ProgressEvent[];
  pointsReward?: PointsReward | null;
  currentProvider?: ProviderSummary | null;
}

export interface ServiceRequestArtifact {
  artifactId: string;
  serviceRequestId: string;
  serviceType: "utility_repair";
  schemaVersion: string;
  version: number;
  status: "draft" | "confirmed" | "superseded";
  summary: string;
  createdBy: string;
  createdAt: string;
}

export interface ServiceRequestProjection {
  serviceRequestId: string;
  conversationId: string;
  serviceType: "utility_repair";
  serviceName: string;
  issueType: string;
  summary: string;
  districtName: string | null;
  preferredTime: string | null;
  safetyHold: boolean;
  provider: ProviderSummary | null;
  pointsReward: PointsReward | null;
  progress: WorkflowProgress;
  createdAt: string;
  updatedAt: string;
}

export interface ProviderTask {
  taskId: string;
  serviceRequestId: string;
  status: string;
  version: number;
  createdAt: string;
  provider: ProviderSummary;
  brief: {
    version: number;
    serviceType: "utility_repair";
    summary: string;
  } | null;
  residentInformation: string | null;
}

export interface ConversationCreated {
  conversationId: string;
  orchestrationMode: "deterministic-demo" | "agentcore-runtime";
  activeAgent: string | null;
  assistantMessage: ApiMessage;
}

export interface ChatTurn {
  conversationId: string;
  orchestrationMode: "deterministic-demo" | "agentcore-runtime";
  activeAgent: string | null;
  assistantMessage: ApiMessage;
  serviceRequest?: ServiceRequestProjection;
  progress?: WorkflowProgress;
  artifact?: ServiceRequestArtifact;
  providerTask?: ProviderTask;
}

export interface ProviderTaskResponse {
  action: "accept" | "decline" | "needs_information";
  expectedVersion: number;
  message?: string;
  arrivalWindow?: string;
  /** 廠商回報的預估實付金額（新台幣元），作為回饋點數的計算基礎；未填則用類別估算。 */
  estimatedAmount?: number;
}
