import { beforeEach, describe, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => ({
  getLastFocused: vi.fn(),
  getCurrent: vi.fn(),
  query: vi.fn(),
  contains: vi.fn(),
  sendMessage: vi.fn(),
  request: vi.fn(),
  remove: vi.fn(),
  openSidebar: vi.fn(),
  isSidebarOpen: vi.fn(),
}));

vi.mock('wxt/browser', () => ({
  browser: {
    windows: { getLastFocused: mocks.getLastFocused, getCurrent: mocks.getCurrent },
    tabs: { query: mocks.query, sendMessage: mocks.sendMessage },
    permissions: { contains: mocks.contains, request: mocks.request, remove: mocks.remove },
    sidebarAction: { open: mocks.openSidebar, isOpen: mocks.isSidebarOpen },
  },
}));

const status = {
  state: 'ARMED', observationCount: 0, organicCount: 0, promotedCount: 0,
  ambiguousCount: 0, hardStopCode: null, startedAt: null, elapsedSeconds: 0,
  autoScroll: false, networkRequests: 0, accountActions: 0,
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
    <button id="sidebar" hidden></button>
  `;
  mocks.getLastFocused.mockResolvedValue({ id: 42, type: 'normal' });
  mocks.getCurrent.mockResolvedValue({ id: 99, type: 'popup' });
  mocks.contains.mockResolvedValue(true);
  mocks.sendMessage.mockResolvedValue({ ok: true, status });
  mocks.isSidebarOpen.mockResolvedValue(false);
  mocks.openSidebar.mockResolvedValue(undefined);
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

  it('opens the Firefox sidebar on an explicit click and refreshes counters while it stays open', async () => {
    mocks.getCurrent.mockResolvedValue({ id: 42, type: 'normal' });
    mocks.query.mockResolvedValue([{ id: 7 }]);
    await import('../entrypoints/popup/main');
    await vi.waitFor(() => expect(document.querySelector('#message')?.textContent).toContain('Ready.'));
    (document.querySelector('#sidebar') as HTMLButtonElement).click();
    expect(mocks.openSidebar).toHaveBeenCalledOnce();
    expect(mocks.getLastFocused).not.toHaveBeenCalled();

    mocks.sendMessage.mockResolvedValue({ ok: true, status: { ...status, state: 'CAPTURING', observationCount: 123, organicCount: 100, promotedCount: 20, ambiguousCount: 3 } });
    tick();
    await vi.waitFor(() => expect(document.querySelector('#total')?.textContent).toBe('123'));
    expect(document.querySelector('#organic')?.textContent).toBe('100');
    expect(document.querySelector('#promoted')?.textContent).toBe('20');
    expect(document.querySelector('#ambiguous')?.textContent).toBe('3');
  });

  it('downloads a complete chunked JSON export from the same X tab', async () => {
    mocks.query.mockResolvedValue([{ id: 7 }]);
    const json = '{"observations":[1,2]}';
    const chunks = [json.slice(0, 11), json.slice(11)];
    mocks.sendMessage.mockImplementation(async (_tabId: number, command: { type: string; index?: number }) => {
      if (command.type === 'XFI_EXPORT') return { ok: true, status: { ...status, observationCount: 2 }, export: { id: 'export-1', sessionId: 'synthetic', chunkCount: 2, totalBytes: new TextEncoder().encode(json).length } };
      if (command.type === 'XFI_EXPORT_CHUNK') return { ok: true, status, chunk: chunks[command.index!] };
      return { ok: true, status: { ...status, observationCount: 2 } };
    });
    const createObjectURL = vi.fn(() => 'blob:synthetic');
    Object.defineProperty(URL, 'createObjectURL', { configurable: true, value: createObjectURL });
    Object.defineProperty(URL, 'revokeObjectURL', { configurable: true, value: vi.fn() });
    const download = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (this: HTMLAnchorElement) {
      expect(this.download).toBe('xfi-synthetic.json');
    });

    await import('../entrypoints/popup/main');
    await vi.waitFor(() => expect(document.querySelector('#total')?.textContent).toBe('2'));
    (document.querySelector('#export') as HTMLButtonElement).click();
    await vi.waitFor(() => expect(document.querySelector('#message')?.textContent).toContain('exported locally'));
    expect(download).toHaveBeenCalledOnce();
    expect(mocks.sendMessage).toHaveBeenCalledWith(7, { type: 'XFI_EXPORT_CHUNK', exportId: 'export-1', index: 0 });
    expect(mocks.sendMessage).toHaveBeenCalledWith(7, { type: 'XFI_EXPORT_CHUNK', exportId: 'export-1', index: 1 });
    expect(createObjectURL).toHaveBeenCalledWith(expect.any(Blob));
  });
});
