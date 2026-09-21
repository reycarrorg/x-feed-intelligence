import { beforeEach, describe, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => ({ sendMessage: vi.fn(), addListener: vi.fn() }));

vi.mock('wxt/browser', () => ({ browser: { runtime: { id: 'test-extension', sendMessage: mocks.sendMessage, onMessage: { addListener: mocks.addListener } } } }));
vi.mock('../lib/parser', () => ({
  SELECTORS: { post: 'article' }, viewportVisibilityRatio: () => 1,
  parseCard: () => ({ platformPostId: '42', canonicalPermalink: 'https://x.com/example/status/42', handle: 'example', displayName: 'Example', displayedTimestamp: 'now', visibleText: 'same visible post', promotion: 'organic', promotionEvidence: 'none', media: [], quote: null, outboundLinks: [], uncertaintyCodes: [], preview: { grade: 'B', reasons: [] } }),
}));

beforeEach(() => {
  vi.stubGlobal('defineContentScript', (definition: unknown) => definition);
  vi.stubGlobal('location', new URL('https://x.com/home'));
  Object.defineProperty(document, 'visibilityState', { configurable: true, value: 'visible' });
  document.body.innerHTML = '';
  mocks.sendMessage.mockReset();
});

describe('page-refresh reconnect', () => {
  it('restores a live tab snapshot, reattaches capture, keeps the count, and never resumes auto-scroll', async () => {
    const snapshot = { revision: 7,
      state: 'CAPTURING', observations: [{ observation_id: 'session-observation-000', platform_post_id: '42', canonical_permalink: 'https://x.com/example/status/42', authors: [{ handle: 'example' }], displayed_timestamp: 'now', visible_text: 'same visible post', promotion: { status: 'organic' }, outbound_links: [], quote_context: null, media: [], uncertainty: [], provenance: [{ provenance_id: 'p' }], relationships: [] }],
      events: [], sessionId: 'session', startedAt: Date.now() - 1000, stoppedAt: null, stopCode: null,
      ambiguousCount: 0, promotionCounts: { organic: 1, promoted: 0, ambiguous: 0 }, observationBytes: 100,
      assistedEver: true, scrollPauseReason: null,
    };
    mocks.sendMessage.mockImplementation(async (message: { type: string }) => message.type === 'XFI_SESSION_READ' ? { snapshot } : { ok: true });
    const { LiveCollector } = await import('../entrypoints/collector.content');
    const collector = new LiveCollector();
    await collector.ready();
    expect(collector.status()).toMatchObject({ state: 'CAPTURING', observationCount: 1, organicCount: 1, autoScroll: false, scrollPauseReason: 'PAGE_RELOADED' });

    const internal = collector as unknown as { ratios: WeakMap<Element, number>; process: (article: Element) => void };
    const replacement = document.createElement('article');
    internal.ratios.set(replacement, 1);
    internal.process(replacement);
    expect(collector.status().observationCount).toBe(1);
    expect(mocks.sendMessage).toHaveBeenCalledWith(expect.objectContaining({ type: 'XFI_SESSION_WRITE' }));
  });

  it('restores a blocked snapshot for export but never resumes capture', async () => {
    const snapshot = { revision: 3, state: 'CAPTURING', sessionId: 'safe-session',
      observations: [{ observation_id: 'safe-post', session_id: 'safe-session', promotion: { status: 'organic' } }],
      events: [], startedAt: Date.now() - 1000, stoppedAt: null, stopCode: null,
      ambiguousCount: 0, promotionCounts: { organic: 1, promoted: 0, ambiguous: 0 }, observationBytes: 100,
      assistedEver: false, scrollPauseReason: null };
    mocks.sendMessage.mockResolvedValue({ snapshot, blocked: true });
    const { LiveCollector } = await import('../entrypoints/collector.content');
    const collector = new LiveCollector();
    await collector.ready();
    expect(collector.status()).toMatchObject({ state: 'ERROR', hardStopCode: 'RETENTION_FAILURE', observationCount: 1 });
    expect((await collector.exportPacket()).ok).toBe(true);
    expect(mocks.sendMessage).toHaveBeenCalledTimes(1);
  });

  it('stops even a terminal session when its latest persistence rejects and sends a session-bound marker', async () => {
    mocks.sendMessage.mockImplementation(async (message: { type: string }) =>
      message.type === 'XFI_SESSION_READ' ? { snapshot: null } :
      message.type === 'XFI_SESSION_WRITE' ? { ok: false, error: 'SESSION_STORAGE_WRITE_FAILED' } : { ok: true });
    const { LiveCollector } = await import('../entrypoints/collector.content');
    const collector = new LiveCollector();
    await collector.ready();
    const internal = collector as unknown as { state: string; sessionId: string; revision: number; persist: () => void };
    internal.state = 'STOPPED';
    internal.sessionId = 'terminal-session';
    internal.persist();
    await vi.waitFor(() => expect(collector.status()).toMatchObject({ state: 'ERROR', hardStopCode: 'RETENTION_FAILURE' }));
    expect(mocks.sendMessage).toHaveBeenCalledWith(expect.objectContaining({ type: 'XFI_SESSION_FAIL_CLOSED', sessionId: 'terminal-session' }));
  });

  it('reports recovery as unconfirmed if both the write and fail-closed marker are rejected', async () => {
    mocks.sendMessage.mockImplementation(async (message: { type: string }) =>
      message.type === 'XFI_SESSION_READ' ? { snapshot: null } : { ok: false, error: 'SESSION_STORAGE_WRITE_FAILED' });
    const { LiveCollector } = await import('../entrypoints/collector.content');
    const collector = new LiveCollector();
    await collector.ready();
    const internal = collector as unknown as { state: string; sessionId: string; persist: () => void };
    internal.state = 'CAPTURING';
    internal.sessionId = 'double-failure-session';
    internal.persist();
    await vi.waitFor(() => expect(collector.status()).toMatchObject({
      state: 'ARMED', pendingState: 'ERROR', pendingPersistenceFailure: true,
    }));
  });

  it('does not let an old-session write failure override a newer session', async () => {
    let rejectOld!: (error: Error) => void;
    mocks.sendMessage.mockImplementation((message: { type: string }) => {
      if (message.type === 'XFI_SESSION_READ') return Promise.resolve({ snapshot: null });
      if (message.type === 'XFI_SESSION_WRITE') return new Promise((_resolve, reject) => { rejectOld = reject; });
      return Promise.resolve({ ok: true });
    });
    const { LiveCollector } = await import('../entrypoints/collector.content');
    const collector = new LiveCollector();
    await collector.ready();
    const internal = collector as unknown as { state: string; sessionId: string; persist: () => void };
    internal.state = 'STOPPED';
    internal.sessionId = 'older-session';
    internal.persist();
    internal.sessionId = 'newer-session';
    internal.state = 'CAPTURING';
    rejectOld(new Error('late rejection'));
    await Promise.resolve();
    expect(collector.status()).toMatchObject({ state: 'ARMED', pendingState: 'CAPTURING', hardStopCode: null });
    expect(mocks.sendMessage).not.toHaveBeenCalledWith(expect.objectContaining({ type: 'XFI_SESSION_FAIL_CLOSED' }));
  });

  it('shows an in-flight card as pending, not saved, before an immediate refresh', async () => {
    let finishWrite!: () => void;
    let storedSnapshot: unknown = null;
    mocks.sendMessage.mockImplementation((message: { type: string; snapshot?: unknown }) => {
      if (message.type === 'XFI_SESSION_READ') return Promise.resolve({ snapshot: storedSnapshot });
      if (message.type === 'XFI_SESSION_WRITE') return new Promise((resolve) => {
        finishWrite = () => { storedSnapshot = message.snapshot; resolve({ ok: true }); };
      });
      return Promise.resolve({ ok: true });
    });
    const { LiveCollector } = await import('../entrypoints/collector.content');
    const firstPage = new LiveCollector();
    await firstPage.ready();
    const internal = firstPage as unknown as { state: string; sessionId: string; startedAt: number;
      ratios: WeakMap<Element, number>; process: (article: Element) => void };
    internal.state = 'CAPTURING';
    internal.sessionId = 'in-flight-session';
    internal.startedAt = Date.now() - 1000;
    const article = document.createElement('article');
    internal.ratios.set(article, 1);
    internal.process(article);
    expect(firstPage.status()).toMatchObject({ observationCount: 0, pendingObservationCount: 1 });
    expect((await firstPage.exportPacket()).ok).toBe(false);
    expect(storedSnapshot).toBeNull();

    const refreshedPage = new LiveCollector();
    await refreshedPage.ready();
    expect(refreshedPage.status().observationCount).toBe(0);
    finishWrite();
  });
});
