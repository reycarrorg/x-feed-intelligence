import { beforeEach, describe, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => ({
  getLastFocused: vi.fn(),
  getCurrent: vi.fn(),
  query: vi.fn(),
  contains: vi.fn(),
  sendMessage: vi.fn(),
  runtimeSend: vi.fn(),
  request: vi.fn(),
  remove: vi.fn(),
  download: vi.fn(),
  search: vi.fn(),
  removeFile: vi.fn(),
  storageGet: vi.fn(),
  storageSet: vi.fn(),
  onChanged: vi.fn(),
  settings: { autoScrollOnStart: false, exportSubfolder: 'XFI' },
}));

vi.mock('wxt/browser', () => ({
  browser: {
    windows: { getLastFocused: mocks.getLastFocused, getCurrent: mocks.getCurrent },
    tabs: { query: mocks.query, sendMessage: mocks.sendMessage },
    runtime: { sendMessage: mocks.runtimeSend },
    permissions: { contains: mocks.contains, request: mocks.request, remove: mocks.remove },
    downloads: { download: mocks.download, search: mocks.search, removeFile: mocks.removeFile, onChanged: { addListener: mocks.onChanged } },
    storage: { local: { get: mocks.storageGet, set: mocks.storageSet } },
  },
}));

const status = {
  state: 'ARMED', observationCount: 0, totalObservationCount: 0, partNumber: 1, organicCount: 0, promotedCount: 0,
  ambiguousCount: 0, hardStopCode: null, startedAt: null, elapsedSeconds: 0,
  autoScroll: false, scrollPauseReason: null, networkRequests: 0, accountActions: 0,
};
let tick: () => void;

beforeEach(() => {
  vi.restoreAllMocks();
  vi.resetModules();
  vi.clearAllMocks();
  vi.spyOn(window, 'setInterval').mockImplementation((handler) => {
    tick = handler as () => void;
    return 1 as unknown as ReturnType<typeof setInterval>;
  });
  document.body.innerHTML = `
    <span id="state"></span><p id="message"></p>
    <strong id="total"></strong><strong id="organic"></strong>
    <strong id="promoted"></strong><strong id="ambiguous"></strong>
    <button id="arm"></button><button id="start"></button>
    <button id="stop"></button><button id="export"></button>
    <button id="discard"></button><button id="revoke"></button>
    <button id="scroll-stop"></button>
    <input id="auto-scroll-setting" type="checkbox" />
    <input id="export-subfolder" type="text" />
    <button id="save-settings"></button><p id="settings-message"></p>
  `;
  mocks.getLastFocused.mockResolvedValue({ id: 42, type: 'normal' });
  mocks.getCurrent.mockResolvedValue({ id: 99, type: 'popup' });
  mocks.contains.mockResolvedValue(true);
  mocks.sendMessage.mockResolvedValue({ ok: true, status });
  mocks.storageGet.mockResolvedValue({});
  mocks.storageSet.mockResolvedValue(undefined);
  mocks.search.mockResolvedValue([]);
  mocks.download.mockResolvedValue(11);
  mocks.runtimeSend.mockResolvedValue({ ok: true, sessionId: 'synthetic' });
});

describe('popup target tab', () => {
  it('uses the active tab of the last focused normal window and confirms its own X collector even without URL metadata', async () => {
    mocks.query.mockResolvedValue([{ id: 7 }]);

    await import('../entrypoints/popup/main');
    await vi.waitFor(() => expect(document.querySelector('#message')?.textContent).toContain('Ready.'));

    expect(mocks.getLastFocused).toHaveBeenCalledWith({ windowTypes: ['normal'] });
    expect(mocks.query).toHaveBeenCalledWith({ active: true, windowId: 42 });
    expect(mocks.sendMessage).toHaveBeenCalledWith(7, { type: 'XFI_STATUS' });
    expect((document.querySelector('#start') as HTMLButtonElement).disabled).toBe(false);
  });

  it('keeps collection disabled when the active tab has no X collector', async () => {
    mocks.query.mockResolvedValue([{ id: 8 }]);
    mocks.sendMessage.mockRejectedValue(new Error('Receiving end does not exist'));

    await import('../entrypoints/popup/main');
    await vi.waitFor(() => expect(document.querySelector('#message')?.textContent).toContain('No X collector is loaded'));

    expect(mocks.sendMessage).toHaveBeenCalledWith(8, { type: 'XFI_STATUS' });
    expect((document.querySelector('#start') as HTMLButtonElement).disabled).toBe(true);
  });

  it('offers exact X access without trusting unavailable tab URL metadata or starting capture', async () => {
    mocks.query.mockResolvedValue([{ id: 7 }]);
    mocks.contains.mockResolvedValue(false);
    mocks.request.mockResolvedValue(true);

    await import('../entrypoints/popup/main');
    await vi.waitFor(() => expect(document.querySelector('#message')?.textContent).toContain('X access is off'));
    const arm = document.querySelector('#arm') as HTMLButtonElement;
    expect(arm.disabled).toBe(false);
    arm.click();
    await vi.waitFor(() => expect(mocks.request).toHaveBeenCalledWith({ origins: ['https://x.com/*'] }));
    expect(mocks.sendMessage).not.toHaveBeenCalled();
    expect((document.querySelector('#start') as HTMLButtonElement).disabled).toBe(true);
  });

  it('keeps controls in the popup and refreshes counters while it stays open', async () => {
    mocks.getCurrent.mockResolvedValue({ id: 42, type: 'normal' });
    mocks.query.mockResolvedValue([{ id: 7 }]);
    await import('../entrypoints/popup/main');
    await vi.waitFor(() => expect(document.querySelector('#message')?.textContent).toContain('Ready.'));
    expect(document.querySelector('#sidebar')).toBeNull();
    expect(mocks.getLastFocused).not.toHaveBeenCalled();

    mocks.sendMessage.mockResolvedValue({ ok: true, status: { ...status, state: 'CAPTURING', observationCount: 123, totalObservationCount: 123, organicCount: 100, promotedCount: 20, ambiguousCount: 3 } });
    tick();
    await vi.waitFor(() => expect(document.querySelector('#total')?.textContent).toBe('123'));
    expect(document.querySelector('#organic')?.textContent).toBe('100');
    expect(document.querySelector('#promoted')?.textContent).toBe('20');
    expect(document.querySelector('#ambiguous')?.textContent).toBe('3');
  });

  it('does not offer the removed in-page control panel', async () => {
    mocks.query.mockResolvedValue([{ id: 7 }]);
    await import('../entrypoints/popup/main');
    await vi.waitFor(() => expect(document.querySelector('#message')?.textContent).toContain('Ready.'));
    expect(document.querySelector('#panel')).toBeNull();
    expect(mocks.sendMessage).not.toHaveBeenCalledWith(7, { type: 'XFI_PANEL_TOGGLE' });
  });

  it('locks export and session-changing controls while an automatic part is being saved', async () => {
    mocks.query.mockResolvedValue([{ id: 7 }]);
    mocks.sendMessage.mockResolvedValue({ ok: true, status: { ...status, state: 'ROLLING_OVER', observationCount: 40, totalObservationCount: 300, partNumber: 2 } });
    await import('../entrypoints/popup/main');
    await vi.waitFor(() => expect(document.querySelector('#message')?.textContent).toContain('Saving part 2'));
    expect((document.querySelector('#export') as HTMLButtonElement).disabled).toBe(true);
    expect((document.querySelector('#discard') as HTMLButtonElement).disabled).toBe(true);
    expect((document.querySelector('#revoke') as HTMLButtonElement).disabled).toBe(true);
  });

  it('hands export to the background without creating a popup-owned blob URL', async () => {
    mocks.query.mockResolvedValue([{ id: 7 }]);
    mocks.sendMessage.mockResolvedValue({ ok: true, status: { ...status, observationCount: 2, totalObservationCount: 2 } });

    await import('../entrypoints/popup/main');
    await vi.waitFor(() => expect(document.querySelector('#total')?.textContent).toBe('2'));
    (document.querySelector('#export') as HTMLButtonElement).click();
    await vi.waitFor(() => expect(document.querySelector('#message')?.textContent).toContain('Export started'));
    expect(mocks.runtimeSend).toHaveBeenCalledWith({ type: 'XFI_SAVE_EXPORT', tabId: 7 });
    expect(mocks.download).not.toHaveBeenCalled();
  });

  it('loads and saves auto-scroll and a default export subfolder in popup settings', async () => {
    mocks.query.mockResolvedValue([{ id: 7 }]);
    mocks.storageGet.mockImplementation(async (key: string) => key === 'xfi_settings_v1'
      ? { xfi_settings_v1: { autoScrollOnStart: true, exportSubfolder: 'Research' } } : {});
    await import('../entrypoints/popup/main');
    await vi.waitFor(() => expect((document.querySelector('#export-subfolder') as HTMLInputElement).value).toBe('Research'));
    expect((document.querySelector('#auto-scroll-setting') as HTMLInputElement).checked).toBe(true);
    (document.querySelector('#export-subfolder') as HTMLInputElement).value = 'XFI-Exports';
    (document.querySelector('#save-settings') as HTMLButtonElement).click();
    await vi.waitFor(() => expect(mocks.storageSet).toHaveBeenCalledWith({ xfi_settings_v1: { autoScrollOnStart: true, exportSubfolder: 'XFI-Exports' } }));
    await vi.waitFor(() => expect(document.querySelector('#settings-message')?.textContent).toContain('Firefox'));
    (document.querySelector('#start') as HTMLButtonElement).click();
    await vi.waitFor(() => expect(mocks.sendMessage).toHaveBeenCalledWith(7, { type: 'XFI_SCROLL_START' }));
  });
});
