import { browser } from 'wxt/browser';
import type { CollectorCommand, CollectorResponse, CollectorStatus, LifecycleState } from '../../lib/contracts';
import { reconcileOwnedExports, startOwnedExport } from '../../lib/export-retention';

const EXACT_PATTERN = 'https://x.com/*';

const elements = {
  state: document.querySelector<HTMLElement>('#state')!,
  message: document.querySelector<HTMLElement>('#message')!,
  total: document.querySelector<HTMLElement>('#total')!,
  organic: document.querySelector<HTMLElement>('#organic')!,
  promoted: document.querySelector<HTMLElement>('#promoted')!,
  ambiguous: document.querySelector<HTMLElement>('#ambiguous')!,
  arm: document.querySelector<HTMLButtonElement>('#arm')!,
  start: document.querySelector<HTMLButtonElement>('#start')!,
  scrollStart: document.querySelector<HTMLButtonElement>('#scroll-start')!,
  scrollStop: document.querySelector<HTMLButtonElement>('#scroll-stop')!,
  stop: document.querySelector<HTMLButtonElement>('#stop')!,
  export: document.querySelector<HTMLButtonElement>('#export')!,
  discard: document.querySelector<HTMLButtonElement>('#discard')!,
  revoke: document.querySelector<HTMLButtonElement>('#revoke')!,
};

let activeTab: { id: number } | null = null;
let confirmedXTab = false;
let permissionGranted = false;
let latestStatus: CollectorStatus | null = null;
let exporting = false;
let refreshing = false;
let lastRefreshDescription = '';
const exportUrls = new Map<number, string>();

function setMessage(value: string): void {
  elements.message.textContent = value;
}

function emptyStatus(state: LifecycleState = permissionGranted ? 'ARMED' : 'INACTIVE'): CollectorStatus {
  return { state, observationCount: 0, organicCount: 0, promotedCount: 0, ambiguousCount: 0, hardStopCode: null, startedAt: null, elapsedSeconds: 0, autoScroll: false, scrollPauseReason: null, networkRequests: 0, accountActions: 0 };
}

function render(status: CollectorStatus): void {
  latestStatus = status;
  elements.state.textContent = status.state.replace('_', ' ');
  elements.state.className = `state ${status.state === 'CAPTURING' ? 'capturing' : status.state === 'ERROR' ? 'error' : ''}`;
  elements.total.textContent = String(status.observationCount);
  elements.organic.textContent = String(status.organicCount);
  elements.promoted.textContent = String(status.promotedCount);
  elements.ambiguous.textContent = String(status.ambiguousCount);

  elements.arm.hidden = permissionGranted;
  elements.arm.disabled = !activeTab;
  elements.start.disabled = !confirmedXTab || !permissionGranted || !['ARMED', 'STOPPED'].includes(status.state);
  elements.stop.disabled = status.state !== 'CAPTURING' && status.state !== 'PAUSED_HIDDEN';
  elements.scrollStart.disabled = status.state !== 'CAPTURING' || status.autoScroll;
  elements.scrollStop.disabled = !status.autoScroll;
  elements.export.disabled = exporting || status.observationCount === 0;
  elements.discard.disabled = status.observationCount === 0 && !['ERROR', 'LIMIT_REACHED', 'STOPPED'].includes(status.state);
  elements.revoke.disabled = !permissionGranted || ['CAPTURING', 'PAUSED_HIDDEN'].includes(status.state);
}

async function send(command: CollectorCommand, tabId = activeTab?.id): Promise<CollectorResponse> {
  if (!tabId) throw new Error('NO_ACTIVE_X_TAB');
  try {
    return await browser.tabs.sendMessage(tabId, command) as CollectorResponse;
  } catch {
    throw new Error('COLLECTOR_NOT_LOADED');
  }
}

async function refresh(): Promise<void> {
  if (refreshing) return;
  refreshing = true;
  try {
    // An action popup can be its own browser window; fall back to the last normal one.
    const currentWindow = await browser.windows.getCurrent();
    const window = currentWindow.type === 'normal' ? currentWindow : await browser.windows.getLastFocused({ windowTypes: ['normal'] });
    const tabs = window.id == null ? [] : await browser.tabs.query({ active: true, windowId: window.id });
    const tab = tabs[0];
    activeTab = tab?.id != null ? { id: tab.id } : null;
    confirmedXTab = false;
    permissionGranted = await browser.permissions.contains({ origins: [EXACT_PATTERN] });
    if (!activeTab) {
      render(emptyStatus());
      describe('Open an https://x.com tab to use the collector.');
      return;
    }
    if (!permissionGranted) {
      render(emptyStatus('INACTIVE'));
      describe('X access is off. Granting it does not start collection; then open or reload an X tab.');
      return;
    }
    try {
      const response = await send({ type: 'XFI_STATUS' });
      if (!response.ok || !response.status) throw new Error('COLLECTOR_NOT_LOADED');
      confirmedXTab = true;
      render(response.status);
      describe(response.status.hardStopCode ? `Stopped safely: ${response.status.hardStopCode}` : response.status.autoScroll ? 'Careful auto-scroll is running while visible cards are captured.' : response.status.state === 'CAPTURING' ? 'Capturing visible cards; scroll manually or opt in to careful auto-scroll.' : 'Ready. Collection starts only when you press Start.');
    } catch {
      render(emptyStatus('INACTIVE'));
      describe('No X collector is loaded in the active tab. Open or reload https://x.com; XFI will reconnect.');
    }
  } catch {
    render(emptyStatus('INACTIVE'));
    describe('Could not locate the active browser tab. Keep an X tab open and retry.');
  } finally {
    refreshing = false;
  }
}

function describe(value: string): void {
  if (value !== lastRefreshDescription) {
    lastRefreshDescription = value;
    setMessage(value);
  }
}

elements.arm.addEventListener('click', async () => {
  permissionGranted = await browser.permissions.request({ origins: [EXACT_PATTERN] });
  render(emptyStatus(permissionGranted ? 'ARMED' : 'INACTIVE'));
  setMessage(permissionGranted ? 'Access granted. Reload this X tab once; XFI will reconnect.' : 'Access was not granted; nothing was collected.');
});

elements.start.addEventListener('click', async () => {
  try {
    const response = await send({ type: 'XFI_START' });
    render(response.status);
    setMessage(response.ok ? 'Capturing only cards that become at least 50% visible while you scroll.' : `Could not start: ${response.error || 'unknown error'}`);
  } catch {
    setMessage('Reload this X tab once so the reviewed collector can load, then try again.');
  }
});

elements.scrollStart.addEventListener('click', async () => {
  try { const response = await send({ type: 'XFI_SCROLL_START' }); render(response.status);
    setMessage(response.ok ? 'Careful auto-scroll started. It stops on hidden tab, challenge, limits, or no progress.' : `Auto-scroll blocked: ${response.error || 'unknown error'}`);
  } catch { setMessage('Return to the collection tab before starting auto-scroll.'); }
});

elements.scrollStop.addEventListener('click', async () => {
  try { const response = await send({ type: 'XFI_SCROLL_STOP' }); render(response.status); setMessage('Auto-scroll stopped; visible capture may continue.'); }
  catch { setMessage('Could not reach the collection tab.'); }
});

elements.stop.addEventListener('click', async () => {
  try {
    const response = await send({ type: 'XFI_STOP' });
    render(response.status);
    setMessage(response.ok ? 'Stopped. Review or export the private packet.' : `Could not stop: ${response.error || 'unknown error'}`);
  } catch {
    setMessage('Return to the collection tab to stop or export its session.');
  }
});

elements.export.addEventListener('click', async () => {
  if (exporting) return;
  const tabId = activeTab?.id;
  if (!tabId) return void setMessage('Select an X tab before exporting.');
  exporting = true;
  elements.export.disabled = true;
  let exportId: string | null = null;
  try {
    setMessage('Preparing local JSON export…');
    const response = await send({ type: 'XFI_EXPORT' }, tabId);
    render(response.status);
    if (!response.ok || !response.export) throw new Error(response.error || 'EXPORT_FAILED');
    const { id, sessionId, chunkCount, totalBytes } = response.export;
    exportId = id;
    const chunks: string[] = [];
    let receivedBytes = 0;
    for (let index = 0; index < chunkCount; index += 1) {
      const part = await send({ type: 'XFI_EXPORT_CHUNK', exportId: id, index }, tabId);
      if (!part.ok || typeof part.chunk !== 'string') throw new Error(part.error || 'EXPORT_CHUNK_FAILED');
      chunks.push(part.chunk);
      receivedBytes += new TextEncoder().encode(part.chunk).length;
    }
    if (receivedBytes !== totalBytes) throw new Error('EXPORT_SIZE_MISMATCH');
    const blob = new Blob([...chunks, '\n'], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    let download: { id: number; sequence: number };
    try {
      download = await startOwnedExport(url);
      exportUrls.set(download.id, url);
    } catch (error) {
      URL.revokeObjectURL(url);
      throw error;
    }
    setMessage(`Save dialog opened for export ${sessionId}. Choose Documents. Older files are recycled only after a new tracked save completes.`);
    window.setTimeout(() => { if (exportUrls.has(download.id)) { exportUrls.delete(download.id); URL.revokeObjectURL(url); } }, 600_000);
    void reconcileOwnedExports().then(({ warning }) => { if (warning) setMessage(warning); });
  } catch (error) {
    setMessage(`Export blocked: ${error instanceof Error ? error.message : 'unknown error'}`);
  } finally {
    if (exportId) {
      try { await send({ type: 'XFI_EXPORT_RELEASE', exportId }, tabId); } catch { /* Tab may have closed. */ }
    }
    exporting = false;
    elements.export.disabled = (latestStatus?.observationCount || 0) === 0;
  }
});

elements.discard.addEventListener('click', async () => {
  try {
    const response = await send({ type: 'XFI_DISCARD' });
    render(response.status);
    setMessage(response.ok ? 'Unsaved session data discarded from the page collector.' : `Could not discard: ${response.error || 'unknown error'}`);
  } catch {
    setMessage('Return to the collection tab before discarding its session.');
  }
});

elements.revoke.addEventListener('click', async () => {
  if (latestStatus && ['CAPTURING', 'PAUSED_HIDDEN'].includes(latestStatus.state)) return void setMessage('Stop collection before revoking access.');
  permissionGranted = !(await browser.permissions.remove({ origins: [EXACT_PATTERN] }));
  render(emptyStatus(permissionGranted ? 'ARMED' : 'INACTIVE'));
  setMessage(permissionGranted ? 'Browser did not revoke access.' : 'X access revoked. No collection can run.');
});

void refresh();
void reconcileOwnedExports().then(({ warning }) => { if (warning) setMessage(warning); }).catch(() => setMessage('Could not verify saved exports; no files were recycled.'));
browser.downloads.onChanged.addListener((delta) => {
  if (delta.state?.current === 'complete' || delta.state?.current === 'interrupted') {
    const url = exportUrls.get(delta.id);
    if (url) { URL.revokeObjectURL(url); exportUrls.delete(delta.id); }
  }
  void reconcileOwnedExports().then(({ warning }) => { if (warning) setMessage(warning); });
});
const refreshTimer = window.setInterval(() => void refresh(), 1000);
window.addEventListener('pagehide', () => window.clearInterval(refreshTimer), { once: true });
