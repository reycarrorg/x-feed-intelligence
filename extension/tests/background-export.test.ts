import { beforeEach, describe, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => ({
  messageListener: null as null | ((message: unknown, sender: { id?: string; tab?: unknown; url?: string }) => Promise<unknown> | undefined),
  changedListener: null as null | ((delta: { id: number; state?: { current: string } }) => void),
  sendTab: vi.fn(), download: vi.fn(), search: vi.fn(), storageGet: vi.fn(), storageSet: vi.fn(),
  sessionGet: vi.fn(),
  ledger: { nextSequence: 1, items: [] as unknown[] },
}));

vi.mock('wxt/browser', () => ({ browser: {
  runtime: { id: 'test-extension', getURL: (path: string) => `moz-extension://test${path}`,
    onMessage: { addListener: (listener: typeof mocks.messageListener) => { mocks.messageListener = listener; } } },
  tabs: { sendMessage: mocks.sendTab },
  downloads: { download: mocks.download, search: mocks.search, removeFile: vi.fn(),
    onChanged: { addListener: (listener: typeof mocks.changedListener) => { mocks.changedListener = listener; } } },
  storage: { local: { get: mocks.storageGet, set: mocks.storageSet }, session: { get: mocks.sessionGet } },
} }));

beforeEach(() => {
  vi.resetModules();
  vi.clearAllMocks();
  vi.stubGlobal('defineBackground', (main: () => void) => { main(); return main; });
  mocks.ledger = { nextSequence: 1, items: [] };
  mocks.storageGet.mockImplementation(async () => ({ xfi_owned_exports_v1: mocks.ledger }));
  mocks.storageSet.mockImplementation(async (value: { xfi_owned_exports_v1: typeof mocks.ledger }) => { mocks.ledger = value.xfi_owned_exports_v1; });
  mocks.search.mockResolvedValue([]);
  mocks.sessionGet.mockResolvedValue({});
  mocks.download.mockResolvedValue(101);
});

describe('background-owned Firefox export', () => {
  it('collects chunks, saves automatically to the default XFI subfolder, and releases its blob after completion', async () => {
    const json = '{"observations":[]}';
    mocks.sendTab.mockImplementation(async (_tabId: number, command: { type: string }) => {
      if (command.type === 'XFI_EXPORT') return { ok: true, export: { id: 'snapshot', sessionId: 'session', chunkCount: 1, totalBytes: json.length } };
      if (command.type === 'XFI_EXPORT_CHUNK') return { ok: true, chunk: json };
      return { ok: true };
    });
    const blobUrl = vi.fn(() => 'blob:moz-extension://test/export');
    const revoke = vi.fn();
    Object.defineProperty(URL, 'createObjectURL', { configurable: true, value: blobUrl });
    Object.defineProperty(URL, 'revokeObjectURL', { configurable: true, value: revoke });
    await import('../entrypoints/background');
    const reply = await mocks.messageListener!({ type: 'XFI_SAVE_EXPORT', tabId: 7 }, { id: 'test-extension', url: 'moz-extension://test/popup.html' });
    expect(reply).toEqual({ ok: true, sessionId: 'session' });
    expect(mocks.download).toHaveBeenCalledWith({ url: 'blob:moz-extension://test/export', filename: 'XFI/xfi-capture-0001.json', saveAs: false, conflictAction: 'uniquify' });
    expect(mocks.sendTab).toHaveBeenCalledWith(7, { type: 'XFI_EXPORT_RELEASE', exportId: 'snapshot' });
    expect(revoke).not.toHaveBeenCalled();
    mocks.changedListener!({ id: 101, state: { current: 'complete' } });
    expect(revoke).toHaveBeenCalledWith('blob:moz-extension://test/export');
  });

  it('rejects messages from a content script or another extension', async () => {
    await import('../entrypoints/background');
    expect(mocks.messageListener!({ type: 'XFI_SAVE_EXPORT', tabId: 7 }, { id: 'test-extension', tab: { id: 7 }, url: 'https://x.com' })).toBeUndefined();
    expect(mocks.messageListener!({ type: 'XFI_SAVE_EXPORT', tabId: 7 }, { id: 'other-extension', url: 'moz-extension://test/popup.html' })).toBeUndefined();
    expect(mocks.download).not.toHaveBeenCalled();
  });

  it('verifies a continuous part completed before acknowledging the next part', async () => {
    const json = '{"observations":[1]}';
    mocks.sendTab.mockImplementation(async (_tabId: number, command: { type: string }) => {
      if (command.type === 'XFI_EXPORT') return { ok: true, export: { id: 'snapshot', sessionId: 'session', chunkCount: 1, totalBytes: json.length } };
      if (command.type === 'XFI_EXPORT_CHUNK') return { ok: true, chunk: json };
      return { ok: true };
    });
    Object.defineProperty(URL, 'createObjectURL', { configurable: true, value: vi.fn(() => 'blob:moz-extension://test/part') });
    Object.defineProperty(URL, 'revokeObjectURL', { configurable: true, value: vi.fn() });
    mocks.sessionGet.mockResolvedValue({
      xfi_tab_session_v1_7: { revision: 2, sessionId: 'session', state: 'ROLLING_OVER', observations: [{}], events: [] },
      xfi_tab_session_v1_owner_7: { clientId: 'client', documentStartedAt: 123 },
    });
    mocks.search.mockResolvedValue([{ id: 101, url: 'blob:moz-extension://test/part', filename: '/Downloads/XFI/xfi-capture-0001.json', state: 'complete' }]);
    await import('../entrypoints/background');
    const reply = await mocks.messageListener!({ type: 'XFI_AUTO_SAVE_EXPORT', clientId: 'client', sessionId: 'session' }, { id: 'test-extension', tab: { id: 7 }, url: 'https://x.com/home' });
    expect(reply).toEqual({ ok: true, sessionId: 'session' });
    expect(mocks.sendTab).toHaveBeenCalledWith(7, { type: 'XFI_ROLLOVER_COMPLETE', sessionId: 'session' });
    expect(mocks.ledger.items).toMatchObject([{ state: 'complete', continuousPart: true }]);
  });

  it('does not accept the removed in-page export command', async () => {
    await import('../entrypoints/background');
    expect(mocks.messageListener!({ type: 'XFI_PANEL_SAVE_EXPORT' }, { id: 'test-extension', tab: { id: 7 }, url: 'https://x.com/home' })).toBeUndefined();
    expect(mocks.messageListener!({ type: 'XFI_PANEL_SAVE_EXPORT' }, { id: 'test-extension', tab: { id: 7 }, url: 'https://example.com/' })).toBeUndefined();
    expect(mocks.sendTab).not.toHaveBeenCalled();
  });
});
