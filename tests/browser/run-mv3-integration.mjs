#!/usr/bin/env node
/* Real, local-only MV3 integration. No ordinary browser profile and no live service origin. */
import {createHash} from "node:crypto";
import {execFileSync} from "node:child_process";
import {readFileSync, writeFileSync, mkdtempSync, readdirSync, rmSync, lstatSync} from "node:fs";
import {createServer as createHttpsServer} from "node:https";
import {createServer as createTcpServer, connect as connectTcp} from "node:net";
import {tmpdir} from "node:os";
import {join, resolve} from "node:path";
import {fileURLToPath} from "node:url";
import {chromium} from "playwright-core";

const root = resolve(fileURLToPath(new URL("../..", import.meta.url)));
const extensionPath = join(root, "harness", "synthetic");
const archivePath = join(root, "build", "browser-quarantine", "chrome-mac-arm64-153.0.8010.36.zip");
const browserPath = join(root, "build", "browser-runtime-153.0.8010.36", "chrome-mac-arm64", "Google Chrome for Testing.app", "Contents", "MacOS", "Google Chrome for Testing");
const expectedArchiveHash = "1f701ef60757c63c6ccf98afaf28291dd0c8d1457d3d738e81fd62201c230ad0";
const expectedBrowserHash = "bfe18f25f912e28e567164f823efbcbf0a87c5292bd66566b6cce7861086d789";
const outputIndex = process.argv.indexOf("--output");
const outputPath = outputIndex >= 0 ? resolve(process.argv[outputIndex + 1]) : null;

function sha256(path) { return createHash("sha256").update(readFileSync(path)).digest("hex"); }
function requireValue(value, message) { if (!value) throw new Error(message); }
function listen(server) { return new Promise((resolvePromise, reject) => { server.once("error", reject); server.listen(0, "127.0.0.1", () => resolvePromise(server.address().port)); }); }
function close(server) { return new Promise((resolvePromise) => server.close(() => resolvePromise())); }
async function clickControl(popup, label) {
  await popup.getByRole("button", {name: label}).focus();
  await popup.keyboard.press("Enter");
  await popup.waitForFunction(() => Boolean(globalThis.__XFI_CONTROL_LAST__));
  const value = await popup.evaluate(() => { const result = globalThis.__XFI_CONTROL_LAST__; delete globalThis.__XFI_CONTROL_LAST__; return result; });
  requireValue(value.response && value.response.ok, "CONTROL_FAILED_" + String(value.response && value.response.code || "NO_RESPONSE"));
  return value.reply;
}

requireValue(!lstatSync(archivePath).isSymbolicLink() && sha256(archivePath) === expectedArchiveHash, "BROWSER_ARCHIVE_INTEGRITY");
requireValue(!lstatSync(browserPath).isSymbolicLink() && sha256(browserPath) === expectedBrowserHash, "BROWSER_EXECUTABLE_INTEGRITY");
const adopted = JSON.parse(readFileSync(join(root, "DEPENDENCIES.lock.json"), "utf8")).test_dependencies.find((item) => item.name === "Chrome for Testing");
requireValue(adopted && adopted.archive_sha256 === expectedArchiveHash && adopted.launcher_sha256 === expectedBrowserHash && adopted.version === "153.0.8010.36", "BROWSER_ADOPTION_DRIFT");

const temporary = mkdtempSync(join(tmpdir(), "xfi-mv3-"));
const profile = join(temporary, "profile");
const cert = join(temporary, "fixture-cert.pem");
const key = join(temporary, "fixture-key.pem");
execFileSync("/usr/bin/openssl", ["req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "1", "-subj", "/CN=fixture.example.invalid", "-addext", "subjectAltName=DNS:fixture.example.invalid", "-keyout", key, "-out", cert], {stdio: "ignore"});
const fixtureHtml = readFileSync(join(extensionPath, "fixture.html"));
let fixtureRequests = 0;
let servedDurationMs = 30000;
const httpsServer = createHttpsServer({key: readFileSync(key), cert: readFileSync(cert)}, (request, response) => {
  if (request.url !== "/") { response.writeHead(404, {"content-type": "text/plain"}); response.end("not found"); return; }
  fixtureRequests += 1;
  response.writeHead(200, {"content-type": "text/html; charset=utf-8", "cache-control": "no-store"});
  response.end(fixtureHtml.toString("utf8").replace('data-fixture-max-duration-ms="30000"', `data-fixture-max-duration-ms="${servedDurationMs}"`));
});
const fixturePort = await listen(httpsServer);
const proxyEvidence = {allowed_fixture_tunnels: 0, denied_requests: 0};
const proxy = createTcpServer((client) => {
  client.once("data", (chunk) => {
    const first = chunk.toString("latin1").split("\r\n", 1)[0];
    if (first === "CONNECT fixture.example.invalid:443 HTTP/1.1") {
      proxyEvidence.allowed_fixture_tunnels += 1;
      const upstream = connectTcp(fixturePort, "127.0.0.1", () => { client.write("HTTP/1.1 200 Connection Established\r\n\r\n"); upstream.write(Buffer.alloc(0)); client.pipe(upstream); upstream.pipe(client); });
      upstream.on("error", () => client.destroy());
      return;
    }
    proxyEvidence.denied_requests += 1;
    client.end("HTTP/1.1 403 Forbidden\r\nConnection: close\r\nContent-Length: 0\r\n\r\n");
  });
});
const proxyPort = await listen(proxy);
requireValue(!readdirSync(temporary).includes("profile"), "PROFILE_NOT_FRESH");

let context;
try {
  context = await chromium.launchPersistentContext(profile, {
    executablePath: browserPath,
    headless: false,
    ignoreHTTPSErrors: true,
    viewport: {width: 1280, height: 1000},
    proxy: {server: `http://127.0.0.1:${proxyPort}`, bypass: ""},
    args: [
      `--disable-extensions-except=${extensionPath}`, `--load-extension=${extensionPath}`, "--disable-quic", "--disable-background-networking",
      "--disable-component-update", "--disable-domain-reliability", "--disable-sync", "--metrics-recording-only", "--no-first-run", "--no-default-browser-check",
      "--disable-features=OptimizationHints,MediaRouter,AutofillServerCommunication,CertificateTransparencyComponentUpdater"
    ],
  });
  let workers = context.serviceWorkers();
  if (!workers.length) workers = [await context.waitForEvent("serviceworker", {timeout: 15000})];
  const extensionId = new URL(workers[0].url()).host;
  const page = context.pages()[0] || await context.newPage();
  await page.goto("https://fixture.example.invalid/", {waitUntil: "domcontentloaded"});
  requireValue(page.url() === "https://fixture.example.invalid/", "RESERVED_HOST_MAPPING_FAILED");
  await page.waitForTimeout(500);
  const popup = await context.newPage();
  await popup.goto(`chrome-extension://${extensionId}/control.html`);
  await clickControl(popup, "Arm synthetic collector");
  await clickControl(popup, "Start synthetic capture");
  await popup.waitForTimeout(500);
  const first = await clickControl(popup, "Export synthetic packet");
  requireValue(first.result.observations.length === 4, "INITIAL_VISIBLE_SET_MISMATCH");
  await page.evaluate(() => {
    const text = document.querySelector('[data-fixture-card="shared-source-001"] [data-fixture-text]').firstChild;
    text.nodeValue = "Deterministic local workshop on day 7 — café 🚀 ";
    document.querySelector('[data-fixture-card="shared-source-001"]').style.color = "rgb(12, 34, 56)";
    document.querySelector(".fixture-display-none").firstChild.nodeValue = "HIDDEN-MUTATED-CANARY";
  });
  await popup.waitForTimeout(250);
  const exported = await clickControl(popup, "Export synthetic packet");
  const envelope = exported.result;
  requireValue(envelope.observations.length === 5, "LATE_CONTENT_NOT_PRESERVED");
  const rendered = JSON.stringify(envelope);
  for (const canary of ["HIDDEN-DISPLAY-CANARY", "HIDDEN-VISIBILITY-CANARY", "HIDDEN-OPACITY-CANARY", "HIDDEN-OFF-LAYOUT-CANARY", "HIDDEN-MUTATED-CANARY"]) requireValue(!rendered.includes(canary), "HIDDEN_TEXT_CAPTURED");
  requireValue(rendered.includes("café 🚀"), "UTF8_OBSERVATION_MISSING");
  const stopped = await clickControl(popup, "Stop synthetic capture");
  requireValue(stopped.snapshot.state === "STOPPED" && stopped.snapshot.observerCount === 0 && stopped.snapshot.timerCount === 0 && stopped.snapshot.domReferenceCount === 0, "STOP_TEARDOWN_FAILED");
  const beforeLate = stopped.snapshot.queueCount;
  await page.evaluate(() => { document.querySelector('[data-fixture-card="shared-source-001"] [data-fixture-text]').firstChild.nodeValue = "post-stop mutation"; });
  await popup.waitForTimeout(150);
  const postStop = await clickControl(popup, "Export synthetic packet");
  requireValue(postStop.snapshot.queueCount === beforeLate && Object.values(postStop.snapshot.effects).every((value) => value === 0), "POST_STOP_EFFECT");
  await clickControl(popup, "Discard synthetic draft");

  await page.reload({waitUntil: "domcontentloaded"});
  await popup.waitForTimeout(150);
  await clickControl(popup, "Arm synthetic collector");
  await clickControl(popup, "Start synthetic capture");
  await popup.waitForTimeout(400);
  await page.evaluate(() => {
    const card = document.querySelector('[data-fixture-card="shared-promoted-001"]');
    card.setAttribute("data-fixture-card", "shared-virtualized-001");
    card.querySelector("[data-fixture-author]").firstChild.nodeValue = "Virtualized Author";
    card.querySelector("[data-fixture-text]").firstChild.nodeValue = "Virtualized node replacement";
    card.querySelector("[data-fixture-promotion]").firstChild.nodeValue = "Organic";
  });
  await popup.waitForTimeout(250);
  const reuse = await clickControl(popup, "Export synthetic packet");
  requireValue(new Set(reuse.result.observations.map((item) => item.platform_post_id)).has("shared-virtualized-001"), "VIRTUALIZED_REUSE_MISSING");
  await clickControl(popup, "Discard synthetic draft");

  servedDurationMs = 80;
  await page.reload({waitUntil: "domcontentloaded"});
  await popup.waitForTimeout(150);
  await clickControl(popup, "Arm synthetic collector");
  await clickControl(popup, "Start synthetic capture");
  await popup.waitForTimeout(200);
  const timerState = await popup.getByRole("button", {name: "Export synthetic packet"}).click().then(async () => { await popup.waitForFunction(() => Boolean(globalThis.__XFI_CONTROL_LAST__)); return popup.evaluate(() => globalThis.__XFI_CONTROL_LAST__); });
  requireValue(timerState.reply.snapshot.state === "ERROR" && timerState.reply.snapshot.events.at(-1).event_code === "DURATION_LIMIT" && timerState.reply.snapshot.timerCount === 0, "ACTUAL_DURATION_TIMER_FAILED");

  if (outputPath) writeFileSync(outputPath, JSON.stringify(envelope, null, 2) + "\n", {flag: "wx"});
  console.log(JSON.stringify({status: "PASS", manifest_version: 3, extension_version: "0.2.0", fresh_profile: true, reserved_host_mapped: true, output_observations: envelope.observations.length, unique_truth_identities: new Set(envelope.observations.map((item) => item.platform_post_id)).size, relationship_edges: envelope.observations.reduce((count, item) => count + item.relationships.length, 0), hidden_canaries_excluded: true, late_content_preserved: true, virtualized_reuse_preserved: true, duration_timer_fired: true, utf8_boundary_exercised: true, teardown_zero: true, post_stop_zero: true, fixture_requests: fixtureRequests, network: proxyEvidence, browser_archive_sha256: expectedArchiveHash, browser_executable_sha256: expectedBrowserHash}));
} finally {
  if (context) await context.close();
  await close(proxy);
  await close(httpsServer);
  rmSync(temporary, {recursive: true, force: true});
}
