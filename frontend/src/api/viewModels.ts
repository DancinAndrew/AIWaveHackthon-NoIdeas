import type { PointsReward, ProviderTask, WorkflowStage } from "./types.ts";


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
    filter: "upcoming",
  },
  awaiting_resident_acceptance: {
    label: "待你驗收",
    color: "#e67e22",
    filter: "upcoming",
  },
  completed: {
    label: "已完成",
    color: "#16a085",
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

export interface PointsRewardPresentation {
  program: string;
  headline: string;
  statusLabel: string;
  /** true 代表點數已入帳（point_status 02），false 為待發放。 */
  granted: boolean;
  basis: string;
  note: string;
  /** true 代表平台內 Demo 記帳，UI 必須明示尚未連動 OPENPOINT 正式帳戶。 */
  demoLedger: boolean;
}

/**
 * 回饋點數的住戶端呈現。金額來源要講清楚，否則住戶會把「平台估算」誤認為報價。
 */
export function pointsRewardPresentation(
  reward: PointsReward,
): PointsRewardPresentation {
  const granted = reward.grantedPoints !== null;
  const points = granted ? reward.grantedPoints! : reward.estimatedPoints;
  const amount = `NT$${reward.basisAmount.toLocaleString("zh-TW")}`;
  const capped = reward.capped
    ? `，已套用單筆上限 ${reward.maxPointsPerOrder} 點`
    : "";
  // 完工金額讓實際點數與預估不同時必須說明，不能靜默換掉數字。
  const adjusted = reward.amountAdjusted
    ? `，原預估 ${reward.estimatedPoints.toLocaleString("zh-TW")} 點`
    : "";
  return {
    program: reward.program,
    headline: granted
      ? `已回饋 ${points.toLocaleString("zh-TW")} 點`
      : `預計回饋 ${points.toLocaleString("zh-TW")} 點`,
    statusLabel: reward.statusLabel,
    granted,
    basis: `${reward.amountSourceLabel} ${amount} × ${reward.earnRate}${capped}${adjusted}`,
    note: reward.isDemoLedger
      ? `${reward.grantCondition} · ${reward.disclosure}`
      : reward.grantCondition,
    demoLedger: reward.isDemoLedger,
  };
}
