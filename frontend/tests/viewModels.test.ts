import assert from "node:assert/strict";
import test from "node:test";

import {
  bookingStatusPresentation,
  pointsRewardPresentation,
  providerTaskPresentation,
} from "../src/api/viewModels.ts";


test("my bookings maps workflow stages to resident-facing labels", () => {
  assert.deepEqual(bookingStatusPresentation("waiting_provider_response"), {
    label: "等待廠商回覆",
    color: "#f39c12",
    filter: "upcoming",
  });
  assert.deepEqual(bookingStatusPresentation("waiting_resident_information"), {
    label: "待補資料",
    color: "#e67e22",
    filter: "upcoming",
  });
  assert.equal(
    bookingStatusPresentation("provider_confirmed").label,
    "廠商已確認",
  );
});

test("provider dashboard preserves task version for optimistic concurrency", () => {
  const view = providerTaskPresentation({
    taskId: "task_123",
    serviceRequestId: "sr_123",
    status: "pending",
    version: 3,
    createdAt: "2026-08-01T12:00:00+00:00",
    provider: { providerId: "provider_1", name: "京鑫水電工程行" },
    brief: {
      version: 2,
      serviceType: "utility_repair",
      summary: "內湖區｜洗手台漏水｜明天下午",
    },
    residentInformation: "總水閥可關閉",
  });

  assert.equal(view.taskId, "task_123");
  assert.equal(view.expectedVersion, 3);
  assert.equal(view.serviceName, "水電修繕");
  assert.match(view.note, /總水閥可關閉/);
});

test("booking card states the points basis and the demo ledger boundary", () => {
  const view = pointsRewardPresentation({
    program: "OPENPOINT",
    status: "01",
    statusLabel: "待發放",
    estimatedPoints: 50,
    grantedPoints: null,
    earnRate: "1%",
    earnRateBasisPoints: 100,
    basisAmount: 5000,
    estimatedBasisAmount: 5000,
    amountSource: "provider_reported",
    amountSourceLabel: "廠商回報預估金額",
    capped: false,
    maxPointsPerOrder: 500,
    amountAdjusted: false,
    grantCondition: "服務完成並經住戶驗收後發放",
    isDemoLedger: true,
    disclosure: "Demo 平台內記帳，尚未連動 OPENPOINT 正式帳戶",
    estimatedAt: "2026-08-02T10:00:00+00:00",
    grantedAt: null,
  });

  assert.equal(view.headline, "預計回饋 50 點");
  assert.equal(view.statusLabel, "待發放");
  assert.match(view.basis, /廠商回報預估金額 NT\$5,000 × 1%/);
  // 住戶必須看得到「還沒發」與「不是正式帳戶」兩件事。
  assert.match(view.note, /驗收後發放/);
  assert.match(view.note, /尚未連動 OPENPOINT 正式帳戶/);
  assert.equal(view.demoLedger, true);
});

test("capped rewards say so instead of silently trimming the number", () => {
  const view = pointsRewardPresentation({
    program: "OPENPOINT",
    status: "01",
    statusLabel: "待發放",
    estimatedPoints: 500,
    grantedPoints: null,
    earnRate: "1%",
    earnRateBasisPoints: 100,
    basisAmount: 1000000,
    estimatedBasisAmount: 1000000,
    amountSource: "provider_reported",
    amountSourceLabel: "廠商回報預估金額",
    capped: true,
    maxPointsPerOrder: 500,
    amountAdjusted: false,
    grantCondition: "服務完成並經住戶驗收後發放",
    isDemoLedger: true,
    disclosure: "Demo 平台內記帳，尚未連動 OPENPOINT 正式帳戶",
    estimatedAt: "2026-08-02T10:00:00+00:00",
    grantedAt: null,
  });

  assert.equal(view.headline, "預計回饋 500 點");
  assert.match(view.basis, /已套用單筆上限 500 點/);
});

const PENDING_REWARD = {
  program: "OPENPOINT",
  status: "01",
  statusLabel: "待發放",
  estimatedPoints: 50,
  grantedPoints: null,
  earnRate: "1%",
  earnRateBasisPoints: 100,
  basisAmount: 5000,
  estimatedBasisAmount: 5000,
  amountSource: "provider_reported",
  amountSourceLabel: "廠商回報預估金額",
  capped: false,
  maxPointsPerOrder: 500,
  amountAdjusted: false,
  grantCondition: "服務完成並經住戶驗收後發放",
  isDemoLedger: true,
  disclosure: "Demo 平台內記帳，尚未連動 OPENPOINT 正式帳戶",
  estimatedAt: "2026-08-02T10:00:00+00:00",
  grantedAt: null,
} as const;

test("granted rewards read as already credited, not as an estimate", () => {
  const view = pointsRewardPresentation({
    ...PENDING_REWARD,
    status: "02",
    statusLabel: "已發放",
    grantedPoints: 62,
    basisAmount: 6200,
    amountAdjusted: true,
    grantCondition: "住戶已驗收，點數已入帳",
    grantedAt: "2026-08-03T09:00:00+00:00",
  });

  assert.equal(view.granted, true);
  assert.equal(view.headline, "已回饋 62 點");
  assert.equal(view.statusLabel, "已發放");
  // 完工金額改變了點數，必須把原預估講出來而不是靜默換數字。
  assert.match(view.basis, /NT\$6,200/);
  assert.match(view.basis, /原預估 50 點/);
  assert.match(view.note, /點數已入帳/);
});

test("pending rewards stay labelled as an estimate", () => {
  const view = pointsRewardPresentation(PENDING_REWARD);

  assert.equal(view.granted, false);
  assert.equal(view.headline, "預計回饋 50 點");
  assert.doesNotMatch(view.basis, /原預估/);
});

test("my bookings separates awaiting acceptance from a completed case", () => {
  assert.deepEqual(bookingStatusPresentation("awaiting_resident_acceptance"), {
    label: "待你驗收",
    color: "#e67e22",
    filter: "upcoming",
  });
  assert.equal(bookingStatusPresentation("completed").filter, "completed");
  // 廠商確認到場還不是完成，不能被歸到「已完成」分頁。
  assert.equal(bookingStatusPresentation("provider_confirmed").filter, "upcoming");
});
