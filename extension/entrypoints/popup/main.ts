import { browser } from 'wxt/browser';
import type { CollectorCommand, CollectorResponse, CollectorStatus, LifecycleState } from '../../lib/contracts';
import { DEFAULT_SETTINGS, getSettings, saveSettings, type XfiSettings } from '../../lib/settings';

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
  scrollStop: document.querySelector<HTMLButtonElement>('#scroll-stop')!,
  stop: document.querySelector<HTMLButtonElement>('#stop')!,
  export: document.querySelector<HTMLButtonElement>('#export')!,
  discard: document.querySelector<HTMLButtonElement>('#discard')!,
  revoke: document.querySelector<HTMLButtonElement>('#revoke')!,
  autoScrollSetting: document.querySelector<HTMLInputElement>('#auto-scroll-setting')!,
  exportSubfolder: document.querySelector<HTMLInputElement>('#export-subfolder')!,
  saveSettings: document.querySelector<HTMLButtonElement>('#save-settings')!,
  settingsMessage: document.querySelector<HTMLElement>('#settings-message')!,
};

let activeTab: { id: number } | null = null;
let confirmedXTab = false;
let permissionGranted = false;
let latestStatus: CollectorStatus | null = null;
let exporting = false;
let refreshing = false;
let lastRefreshDescription = '';
let currentSettings: XfiSettings = DEFAULT_SETTINGS;

function setMessage(value: string): void {
  elements.message.textContent = value;
}

function emptyStatus(state: LifecycleState = permissionGranted ? 'ARMED' : 'INACTIVE'): CollectorStatus {
  return { state, pendingState: null, pendingObservationCount: 0, pendingChanges: false, pendingPersistenceFailure: false, observationCount: 0, totalObservationCount: 0, partNumber: 1, organicCount: 0, promotedCount: 0, ambiguousCount: 0, hardStopCode: null, startedAt: null, elapsedSeconds: 0, autoScroll: false, scrollPauseReason: null, networkRequests: 0, accountActions: 0 };
}

function render(status: CollectorStatus): void {
  latestStatus = status;
  const activeState = status.pendingState || status.state;
  elements.state.textContent = status.pendingState ? `${status.state.replace('_', ' ')} (${status.pendingState.replace('_', ' ')} pending)` : status.state.replace('_', ' ');
  elements.state.className = `state ${activeState === 'CAPTURING' ? 'capturing' : activeState === 'ERROR' ? 'error' : ''}`;
  elements.total.textContent = String(status.totalObservationCount);
  elements.organic.textContent = String(status.organicCount);
  elements.promoted.textContent = String(status.promotedCount);
  elements.ambiguous.textContent = String(status.ambiguousCount);

  elements.arm.hidden = permissionGranted;
  elements.arm.disabled = !activeTab;
  elements.start.disabled = !confirmedXTab || !permissionGranted || !['ARMED', 'STOPPED'].includes(activeState);
  elements.stop.disabled = activeState !== 'CAPTURING' && activeState !== 'PAUSED_HIDDEN' && activeState !== 'ROLLING_OVER';
  elements.scrollStop.disabled = !status.autoScroll;
  elements.export.disabled = exporting || activeState === 'ROLLING_OVER' || status.observationCount === 0;
  elements.discard.disabled = activeState === 'ROLLING_OVER' || (status.observationCount === 0 && !['ERROR', 'LIMIT_REACHED', 'STOPPED'].includes(activeState));
  elements.revoke.disabled = !permissionGranted || ['CAPTURING', 'PAUSED_HIDDEN', 'ROLLING_OVER'].includes(activeState);
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
      describe(response.status.pendingPersistenceFailure ? 'Storage failed; capture stopped in this page. Recovery blocking is unconfirmed, so export the saved count now.' : response.status.hardStopCode === 'RETENTION_FAILURE' ? 'Storage failed; capture is blocked. Only the saved count is available to export.' : response.status.pendingObservationCount > 0 ? `${response.status.pendingObservationCount} card(s) pending storage; only the saved count survives refresh.` : response.status.pendingState ? `${response.status.pendingState.replace('_', ' ')} pending storage; wait for confirmation before refreshing.` : response.status.pendingChanges ? 'Updates pending storage; only the saved version survives refresh.' : response.status.state === 'ROLLING_OVER' ? `Saving part ${response.status.partNumber}; capture resumes after Firefox confirms the file.` : response.status.hardStopCode === 'REFRESH_RECOVERY_LIMIT' ? 'Stopped before the 9 MiB refresh-safe limit. Export this private packet before starting another session.' : response.status.hardStopCode ? `Stopped safely: ${response.status.hardStopCode}` : response.status.autoScroll && response.status.scrollPauseReason === 'NO_SCROLL_MOVEMENT' ? 'Careful auto-scroll found no movement and is slowing down; it stops if progress does not resume.' : response.status.autoScroll && response.status.scrollPauseReason === 'NESTED_FEED_SCROLL' ? 'Careful auto-scroll is advancing the visible feed container.' : response.status.autoScroll ? 'Careful auto-scroll is advancing the page while visible cards are captured.' : response.status.state === 'CAPTURING' ? 'Capturing visible cards; scrolling follows your saved setting.' : 'Ready. Collection starts only when you press Start.');
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
    if (!response.ok) return void setMessage(`Could not start: ${response.error || 'unknown error'}`);
    if (currentSettings.autoScrollOnStart) {
      const scroll = await send({ type: 'XFI_SCROLL_START' });
      render(scroll.status);
      setMessage(scroll.ok ? 'Capturing visible cards with hands-free scrolling. Move the mouse or press a key to stop scrolling.' : `Capture started; hands-free scrolling did not: ${scroll.error || 'unknown error'}`);
    } else setMessage('Capturing only cards that become at least 50% visible while you scroll.');
  } catch {
    setMessage('Reload this X tab once so the reviewed collector can load, then try again.');
  }
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
  try {
    setMessage('Preparing automatic local JSON export…');
    const reply = await browser.runtime.sendMessage({ type: 'XFI_SAVE_EXPORT', tabId }) as { ok: boolean; sessionId?: string; error?: string };
    if (!reply?.ok) throw new Error(reply?.error || 'EXPORT_FAILED');
    setMessage(`Export started for ${reply.sessionId} in your configured browser download subfolder. Only older standalone exports may be recycled after ten verified saves; continuous parts are kept.`);
  } catch (error) {
    setMessage(`Export blocked: ${error instanceof Error ? error.message : 'unknown error'}`);
  } finally {
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

elements.saveSettings.addEventListener('click', async () => {
  try {
    const next = { autoScrollOnStart: elements.autoScrollSetting.checked, exportSubfolder: elements.exportSubfolder.value };
    await saveSettings(next);
    currentSettings = next;
    elements.settingsMessage.textContent = 'Saved. Exports use this subfolder under Firefox’s download location.';
    if (latestStatus?.state === 'CAPTURING') {
      const command = next.autoScrollOnStart ? 'XFI_SCROLL_START' : 'XFI_SCROLL_STOP';
      const response = await send({ type: command });
      render(response.status);
    }
  } catch (error) {
    elements.settingsMessage.textContent = error instanceof Error ? error.message : 'Could not save settings.';
  }
});

void getSettings().then((settings) => {
  currentSettings = settings;
  elements.autoScrollSetting.checked = settings.autoScrollOnStart;
  elements.exportSubfolder.value = settings.exportSubfolder;
}).catch(() => { elements.settingsMessage.textContent = 'Could not load settings; defaults are shown.'; });

void refresh();
const refreshTimer = window.setInterval(() => void refresh(), 1000);
window.addEventListener('pagehide', () => window.clearInterval(refreshTimer), { once: true });
