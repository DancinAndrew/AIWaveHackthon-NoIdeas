export type WorkflowStage =
  | "collecting_details"
  | "safety_hold"
  | "awaiting_resident_confirmation"
  | "waiting_provider_response"
  | "waiting_resident_information"
  | "rematching"
  | "provider_confirmed";

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

export interface WorkflowProgress {
  serviceRequestId: string;
  stage: WorkflowStage;
  waitingFor: "resident" | "provider" | "admin" | null;
  displayLabel: string;
  residentActionRequired: boolean;
  latestEventAt: string;
  events?: ProgressEvent[];
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
  orchestrationMode: "deterministic-demo" | "agentcore";
  activeAgent: string | null;
  assistantMessage: ApiMessage;
}

export interface ChatTurn {
  conversationId: string;
  orchestrationMode: "deterministic-demo" | "agentcore";
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
}
