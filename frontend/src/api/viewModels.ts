import type { ProviderTask, WorkflowStage } from "./types.ts";


export interface BookingStatusPresentation {
  label: string;
  color: string;
  filter: "upcoming" | "completed";
}

const BOOKING_STATUS: Record<WorkflowStage, BookingStatusPresentation> = {
  collecting_details: {
    label: "需求確認中",
    color: "#8e44ad",
    filter: "upcoming",
  },
  safety_hold: {
    label: "安全暫停",
    color: "#e74c3c",
    filter: "upcoming",
  },
  awaiting_resident_confirmation: {
    label: "待確認文件",
    color: "#e67e22",
    filter: "upcoming",
  },
  waiting_provider_response: {
    label: "等待廠商回覆",
    color: "#f39c12",
    filter: "upcoming",
  },
  waiting_resident_information: {
    label: "待補資料",
    color: "#e67e22",
    filter: "upcoming",
  },
  rematching: {
    label: "改派中",
    color: "#2980b9",
    filter: "upcoming",
  },
  provider_confirmed: {
    label: "廠商已確認",
    color: "#27ae60",
    filter: "completed",
  },
};

export function bookingStatusPresentation(
  stage: WorkflowStage,
): BookingStatusPresentation {
  return BOOKING_STATUS[stage];
}

export interface ProviderTaskPresentation {
  taskId: string;
  serviceRequestId: string;
  expectedVersion: number;
  serviceName: string;
  summary: string;
  note: string;
  createdAt: string;
}

export function providerTaskPresentation(
  task: ProviderTask,
): ProviderTaskPresentation {
  return {
    taskId: task.taskId,
    serviceRequestId: task.serviceRequestId,
    expectedVersion: task.version,
    serviceName:
      task.brief?.serviceType === "utility_repair" ? "水電修繕" : "其他服務",
    summary: task.brief?.summary ?? "需求文件準備中",
    note: task.residentInformation
      ? `住戶補充：${task.residentInformation}`
      : `需求文件版本：v${task.brief?.version ?? 1}`,
    createdAt: task.createdAt,
  };
}
