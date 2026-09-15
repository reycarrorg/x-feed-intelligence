import { browser } from 'wxt/browser';
import type { CollectorCommand, CollectorResponse, CollectorStatus, LifecycleState } from '../../lib/contracts';

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
  stop: document.querySelector<HTMLButtonElement>('#stop')!,
  export: document.querySelector<HTMLButtonElement>('#export')!,
  discard: document.querySelector<HTMLButtonElement>('#discard')!,
  revoke: document.querySelector<HTMLButtonElement>('#revoke')!,
};

let activeTab: { id: number; url: string } | null = null;
let permissionGranted = false;
let latestStatus: CollectorStatus | null = null;

function isXUrl(url: string): boolean {
  try {
    const parsed = new URL(url);
    return parsed.protocol === 'https:' && parsed.hostname === 'x.com';
  } catch {
    return false;
  }
}

function setMessage(value: string): void {
  elements.message.textContent = value;
}

function emptyStatus(state: LifecycleState = permissionGranted ? 'ARMED' : 'INACTIVE'): CollectorStatus {
  return { state, observationCount: 0, organicCount: 0, promotedCount: 0, ambiguousCount: 0, hardStopCode: null, startedAt: null, elapsedSeconds: 0, autoScroll: false, networkRequests: 0, accountActions: 0 };
}

function render(status: CollectorStatus): void {
  latestStatus = status;
  elements.state.textContent = status.state.replace('_', ' ');
  elements.state.className = `state ${status.state === 'CAPTURING' ? 'capturing' : status.state === 'ERROR' ? 'error' : ''}`;
  elements.total.textContent = String(status.observationCount);
  elements.organic.textContent = String(status.organicCount);
  elements.promoted.textContent = String(status.promotedCount);
  elements.ambiguous.textContent = String(status.ambiguousCount);

  const active = isXUrl(activeTab?.url || '');
  elements.arm.hidden = permissionGranted;
  elements.arm.disabled = !active;
  elements.start.disabled = !active || !permissionGranted || !['ARMED', 'STOPPED'].includes(status.state);
  elements.stop.disabled = status.state !== 'CAPTURING' && status.state !== 'PAUSED_HIDDEN';
  elements.export.disabled = status.observationCount === 0;
  elements.discard.disabled = status.observationCount === 0 && !['ERROR', 'LIMIT_REACHED', 'STOPPED'].includes(status.state);
  elements.revoke.disabled = !permissionGranted || ['CAPTURING', 'PAUSED_HIDDEN'].includes(status.state);
}

async function send(command: CollectorCommand): Promise<CollectorResponse> {
  if (!activeTab?.id) throw new Error('NO_ACTIVE_X_TAB');
  try {
    return await browser.tabs.sendMessage(activeTab.id, command) as CollectorResponse;
  } catch {
    throw new Error('COLLECTOR_NOT_LOADED');
  }
}

async function refresh(): Promise<void> {
  const tabs = await browser.tabs.query({ active: true, currentWindow: true });
  const tab = tabs[0];
  activeTab = tab?.id != null && tab.url ? { id: tab.id, url: tab.url } : null;
  permissionGranted = await browser.permissions.contains({ origins: [EXACT_PATTERN] });
  if (!isXUrl(activeTab?.url || '')) {
    render(emptyStatus());
    setMessage('Open an https://x.com tab to use the collector.');
    return;
  }
  if (!permissionGranted) {
    render(emptyStatus('INACTIVE'));
    setMessage('Access is off. Granting access does not start collection.');
    return;
  }
  try {
    const response = await send({ type: 'XFI_STATUS' });
    render(response.status);
    setMessage(response.status.hardStopCode ? `Stopped safely: ${response.status.hardStopCode}` : response.status.state === 'CAPTURING' ? 'Capturing visible cards while you scroll normally.' : 'Ready. Collection starts only when you press Start.');
  } catch {
    render(emptyStatus('ARMED'));
    setMessage('Access is granted. Reload this X tab once, then reopen XFI.');
  }
}

elements.arm.addEventListener('click', async () => {
  permissionGranted = await browser.permissions.request({ origins: [EXACT_PATTERN] });
  render(emptyStatus(permissionGranted ? 'ARMED' : 'INACTIVE'));
  setMessage(permissionGranted ? 'Access granted. Reload this X tab once, then reopen XFI.' : 'Access was not granted; nothing was collected.');
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

elements.stop.addEventListener('click', async () => {
  const response = await send({ type: 'XFI_STOP' });
  render(response.status);
  setMessage('Stopped. Review or export the private packet.');
});

elements.export.addEventListener('click', async () => {
  const response = await send({ type: 'XFI_EXPORT' });
  render(response.status);
  if (!response.ok || !response.packet) return void setMessage(`Export blocked: ${response.error || 'unknown error'}`);
  const blob = new Blob([`${JSON.stringify(response.packet, null, 2)}\n`], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  const session = (response.packet.session as { session_id?: string } | undefined)?.session_id || 'session';
  anchor.href = url;
  anchor.download = `xfi-${session}.json`;
  anchor.click();
  URL.revokeObjectURL(url);
  setMessage('Private JSON exported locally. It has not been uploaded or analyzed yet.');
});

elements.discard.addEventListener('click', async () => {
  const response = await send({ type: 'XFI_DISCARD' });
  render(response.status);
  setMessage('Unsaved session data discarded from the page collector.');
});

elements.revoke.addEventListener('click', async () => {
  if (latestStatus && ['CAPTURING', 'PAUSED_HIDDEN'].includes(latestStatus.state)) return void setMessage('Stop collection before revoking access.');
  permissionGranted = !(await browser.permissions.remove({ origins: [EXACT_PATTERN] }));
  render(emptyStatus(permissionGranted ? 'ARMED' : 'INACTIVE'));
  setMessage(permissionGranted ? 'Chrome did not revoke access.' : 'X access revoked. No collection can run.');
});

void refresh();
