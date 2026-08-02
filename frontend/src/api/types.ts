/** Every service type the platform plans to support. */
export type ServiceType =
  | "utility_repair"
  | "product_purchase"
  | "restaurant_reservation"
  | "housekeeping_service"
  | "community_consultation";

export type WorkflowStage =
  // Shared across service types.
  | "collecting_details"
  | "awaiting_resident_confirmation"
  | "waiting_provider_response"
  | "waiting_resident_information"
  | "rematching"
  | "provider_confirmed"
  // Utility repair only.
  | "safety_hold"
  // Product purchase only.
  | "awaiting_resident_selection"
  | "authorizing_payment"
  | "out_of_stock";

/**
 * Competition `mms_order_record.order_status` values for `order_type = '05'`.
 * The MVP acceptance end point is `03`.
 */
export type ProductOrderStatus =
  | "01"
  | "02"
  | "03"
  | "04"
  | "80"
  | "90"
  | "99";

/**
 * One ranked purchase option. Every amount is computed by the backend from the
 * catalogue, so the UI only ever displays these values and never recomputes or
 * submits them.
 */
export interface ProductCandidate {
  sku: string;
  name: string;
  brand: string;
  itemType: string;
  category: string;
  specs: Record<string, string>;
  supplierId: string;
  supplierName: string;
  rating: number;
  warrantyMonths: number;
  returnPolicyLabel: string;
  available: number;
  score: number;
  reasons: string[];
  ruleVersion: string;
  quantity: number;
  /** Catalogue list price for one unit, before any promotion. */
  listPrice: number;
  /** Unit price after any applicable promotion. */
  unitPrice: number;
  originalAmount: number;
  discountAmount: number;
  shippingFeeAmount: number;
  finalAmount: number;
  currency: string;
  promotionApplied: boolean;
  promotionLabel: string | null;
  freeShippingApplied: boolean;
  /** "promotion" when a free-shipping promotion waives the fee. */
  freeShippingSource: "promotion" | "threshold" | null;
  freeShippingThreshold: number;
  deliveryCode: string;
  deliveryLabel: string;
  estimatedDays: number;
  coldChain: boolean;
}

export interface ApiMessage {
  messageId: string;
  conversationId: string;
  role: "user" | "assistant";
  content: string;
  agent: string | null;
  kind: "message" | "final";
  createdAt: string;
}

/**
 * Demo-only role-switching entry. Carries no credentials; the backend derives
 * authorization from the actor context, not from this list.
 */
export interface DemoProvider {
  providerId: string;
  name: string;
  serviceType: ServiceType;
  serviceName: string;
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
  serviceType: ServiceType;
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
  serviceType: ServiceType;
  serviceName: string;
  summary: string;
  provider: ProviderSummary | null;
  progress: WorkflowProgress;
  safetyHold: boolean;
  createdAt: string;
  updatedAt: string;

  // Utility repair fields. Absent for other service types.
  issueType?: string;
  preferredTime?: string | null;

  // Shared by utility repair (service area) and product purchase (delivery).
  districtName?: string | null;

  // Product purchase fields.
  itemType?: string | null;
  category?: string | null;
  quantity?: number;
  candidates?: ProductCandidate[];
  candidatesVersion?: number;
  selectedSku?: string | null;
  orderNo?: string | null;
  orderStatus?: ProductOrderStatus | null;
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
    serviceType: ServiceType;
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
  /** Required when a utility provider accepts. */
  arrivalWindow?: string;
  /** Required when a product supplier accepts. */
  estimatedShipDate?: string;
}

/**
 * Result of choosing one candidate. The request carries only the identifier and
 * the expected version; the backend recomputes every amount, so no price field
 * is ever sent.
 */
export interface SelectionResult {
  serviceRequestId: string;
  progress: WorkflowProgress;
  serviceRequest: ServiceRequestProjection;
  artifact: ServiceRequestArtifact & {
    canonical?: Record<string, unknown>;
  };
  assistantMessage: ApiMessage;
}
