import assert from "node:assert/strict";


const playwrightModule = process.env.PLAYWRIGHT_MODULE ?? "playwright";
const chromeExecutable =
  process.env.CHROME_EXECUTABLE ??
  "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const frontendUrl = process.env.FRONTEND_URL ?? "http://127.0.0.1:5173";
const screenshotDir = process.env.E2E_SCREENSHOT_DIR ?? "/tmp/aiwave-e2e";

const { chromium } = await import(playwrightModule);
const browser = await chromium.launch({
  headless: true,
  executablePath: chromeExecutable,
});
const page = await browser.newPage({ viewport: { width: 430, height: 900 } });

async function send(message) {
  await page.getByPlaceholder(/浴室洗手台|輸入訊息/).fill(message);
  await page.getByRole("button", { name: "傳送" }).click();
}

try {
  await page.goto(frontendUrl, { waitUntil: "networkidle" });
  await page.evaluate(() => window.localStorage.clear());
  await page.reload({ waitUntil: "networkidle" });
  await page.getByRole("button", { name: "AI 智慧助理" }).click();
  await page.locator(".chat-title").getByText("智慧助理", { exact: true }).waitFor();

  await send("我家浴室洗手台下方水管一直漏水");
  await page.getByText(/先確認用電安全/).waitFor();
  await send("沒有漏電、冒煙或積水，水量不大");
  await page.getByText(/服務地區/).waitFor();
  await send("台北市內湖區");
  await page.getByText(/日期與時段/).waitFor();
  await send("明天下午兩點到五點都可以");
  await page.getByText(/水電需求文件 v1/).waitFor();
  await send("確認送出");
  await page.getByText(/等待廠商回覆/).waitFor();
  await page.screenshot({
    path: `${screenshotDir}/chat-waiting-provider.png`,
    fullPage: true,
  });

  await page.getByText("查看進度 ›").click();
  await page.getByText("我的預約", { exact: true }).waitFor();
  await page.getByText("等待廠商回覆", { exact: true }).first().waitFor();
  await page.screenshot({
    path: `${screenshotDir}/my-bookings-waiting.png`,
    fullPage: true,
  });

  await page.goto(`${frontendUrl}/`, { waitUntil: "networkidle" });
  await page.locator(".phone-frame").evaluate((element) => {
    element.scrollTop = element.scrollHeight;
  });
  await page.screenshot({
    path: `${screenshotDir}/home-shortcuts.png`,
    fullPage: true,
  });
  const shortcuts = page.getByText("後台管理", { exact: true });
  assert.equal(await shortcuts.count(), 1);
  await shortcuts.click();
  await page.getByText("候選派工", { exact: true }).waitFor();
  await page.screenshot({
    path: `${screenshotDir}/provider-dashboard.png`,
    fullPage: true,
  });
  await page.getByPlaceholder("例如：總水閥是否能關閉？").fill(
    "請問總水閥是否能關閉？",
  );
  await page.getByRole("button", { name: "補問" }).click();
  await page.getByText("待住戶補充", { exact: true }).waitFor();

  await page.goto(`${frontendUrl}/chat`, { waitUntil: "networkidle" });
  await page.getByText(/總水閥是否能關閉/).waitFor({ timeout: 7000 });
  await send("可以，總水閥在門外");
  await page.getByText(/回傳給原廠商/).waitFor();

  await page.goto(`${frontendUrl}/dashboard`, { waitUntil: "networkidle" });
  await page.getByText("候選派工", { exact: true }).waitFor({ timeout: 7000 });
  await page.getByPlaceholder("2026-08-03 14:00-17:00").fill(
    "2026-08-03 14:00-17:00",
  );
  await page.getByRole("button", { name: "接受" }).click();
  await page.getByText("已接受", { exact: true }).waitFor();

  await page.goto(`${frontendUrl}/chat`, { waitUntil: "networkidle" });
  await page.getByText(/平台內確認/).waitFor({ timeout: 7000 });
  await page.screenshot({
    path: `${screenshotDir}/chat-provider-confirmed.png`,
    fullPage: true,
  });

  await page.goto(`${frontendUrl}/my-bookings`, { waitUntil: "networkidle" });
  await page.getByText("廠商已確認", { exact: true }).first().waitFor();
  await page.screenshot({
    path: `${screenshotDir}/my-bookings-confirmed.png`,
    fullPage: true,
  });

  console.log("utility walkthrough E2E passed");
} finally {
  await browser.close();
}
