import assert from "node:assert/strict";
import test from "node:test";

import {
  bookingStatusPresentation,
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
