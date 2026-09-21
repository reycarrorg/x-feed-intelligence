import { beforeEach, expect, it, vi } from 'vitest';

type BackgroundListener = (message: unknown, sender: { id: string; tab: { id: number } }) => Promise<unknown> | undefined;
const mocks = vi.hoisted(() => ({
  backgroundListener: null as BackgroundListener | null,
  stored: new Map<string, unknown>(),
  sendRuntime: vi.fn(),
  get: vi.fn(), set: vi.fn(), remove: vi.fn(),
}));

vi.mock('wxt/browser', () => ({ browser: {
  runtime: { id: 'test-extension', sendMessage: mocks.sendRuntime,
    onMessage: { addListener: (listener: BackgroundListener) => { mocks.backgroundListener = listener; } } },
  storage: { session: { get: mocks.get, set: mocks.set, remove: mocks.remove },
    local: { get: vi.fn(async () => ({ xfi_owned_exports_v1: { nextSequence: 1, items: [] } })), set: vi.fn(async () => undefined) } },
  downloads: { onChanged: { addListener: vi.fn() } },
  tabs: { onRemoved: { addListener: vi.fn() } },
} }));
vi.mock('../lib/parser', () => ({
  SELECTORS: { post: 'article' }, viewportVisibilityRatio: () => 1,
  parseCard: (article: HTMLElement) => ({ platformPostId: article.dataset.postId, canonicalPermalink: `https://x.com/example/status/${article.dataset.postId}`,
    handle: 'example', displayName: 'Example', displayedTimestamp: 'now', visibleText: article.dataset.visibleText || `Visible ${article.dataset.postId}`,
    promotion: 'organic', promotionEvidence: 'none', media: [], quote: null, outboundLinks: [], uncertaintyCodes: [], preview: { grade: 'B', reasons: [] } }),
}));

function setDocumentStart(value: number): void {
  Object.defineProperty(performance, 'timeOrigin', { configurable: true, value });
}

beforeEach(() => {
  vi.resetModules();
  vi.clearAllMocks();
  mocks.stored.clear();
  vi.stubGlobal('defineBackground', (main: () => void) => { main(); return main; });
  vi.stubGlobal('defineContentScript', (definition: unknown) => definition);
  vi.stubGlobal('location', new URL('https://x.com/home'));
  setDocumentStart(1000);
  Object.defineProperty(document, 'visibilityState', { configurable: true, value: 'visible' });
  document.body.innerHTML = '';
  mocks.get.mockImplementation(async (keys: string | string[]) => Object.fromEntries(
    (Array.isArray(keys) ? keys : [keys]).filter((key) => mocks.stored.has(key)).map((key) => [key, mocks.stored.get(key)])));
  mocks.set.mockImplementation(async (items: Record<string, unknown>) => { for (const [key, value] of Object.entries(items)) mocks.stored.set(key, value); });
  mocks.remove.mockImplementation(async (keys: string | string[]) => { for (const key of Array.isArray(keys) ? keys : [keys]) mocks.stored.delete(key); });
  mocks.sendRuntime.mockImplementation((message: unknown) => mocks.backgroundListener!(message, { id: 'test-extension', tab: { id: 7 } }));
});

it('commits a visible count through the background store and restores exactly that count on a new page', async () => {
  await import('../entrypoints/background');
  const { LiveCollector } = await import('../entrypoints/collector.content');
  const page = new LiveCollector();
  await page.ready();
  const internal = page as unknown as { state: string; sessionId: string; startedAt: number;
    ratios: WeakMap<Element, number>; process: (article: Element) => void };
  internal.state = 'CAPTURING';
  internal.sessionId = 'roundtrip-session';
  internal.startedAt = Date.now() - 1000;
  const article = document.createElement('article');
  article.dataset.postId = '1';
  internal.ratios.set(article, 1);
  internal.process(article);
  expect(page.status()).toMatchObject({ observationCount: 0, pendingObservationCount: 1 });
  await vi.waitFor(() => expect(page.status()).toMatchObject({ observationCount: 1, pendingObservationCount: 0 }));
  const savedExport = await page.exportPacket();
  expect(savedExport.ok).toBe(true);

  setDocumentStart(2000);
  const refreshed = new LiveCollector();
  await refreshed.ready();
  expect(refreshed.status()).toMatchObject({ state: 'CAPTURING', observationCount: 1, pendingObservationCount: 0 });
  expect((await refreshed.exportPacket()).ok).toBe(true);
});

it('never displays or exports a second card whose write has not reached storage before refresh', async () => {
  await import('../entrypoints/background');
  const { LiveCollector } = await import('../entrypoints/collector.content');
  const page = new LiveCollector();
  await page.ready();
  const internal = page as unknown as { state: string; sessionId: string; startedAt: number;
    ratios: WeakMap<Element, number>; process: (article: Element) => void };
  internal.state = 'CAPTURING';
  internal.sessionId = 'two-card-session';
  internal.startedAt = Date.now() - 1000;
  const article = document.createElement('article');
  internal.ratios.set(article, 1);
  article.dataset.postId = '1';
  internal.process(article);
  await vi.waitFor(() => expect(page.status().observationCount).toBe(1));
  let deliverSecond!: () => Promise<unknown>;
  mocks.sendRuntime.mockImplementation((message: { type: string }) => {
    if (message.type === 'XFI_SESSION_WRITE') return new Promise((resolve) => {
      deliverSecond = async () => {
        const reply = await mocks.backgroundListener!(message, { id: 'test-extension', tab: { id: 7 } });
        resolve(reply);
        return reply;
      };
    });
    return mocks.backgroundListener!(message, { id: 'test-extension', tab: { id: 7 } });
  });
  article.dataset.postId = '2';
  internal.process(article);
  const deliverOld = deliverSecond;
  expect(page.status()).toMatchObject({ observationCount: 1, pendingObservationCount: 1 });
  const exportBeforeRefresh = await page.exportPacket();
  const json = Array.from({ length: exportBeforeRefresh.export!.chunkCount }, (_, index) => page.exportChunk(exportBeforeRefresh.export!.id, index).chunk).join('');
  expect((JSON.parse(json) as { observations: unknown[] }).observations).toHaveLength(1);
  setDocumentStart(2000);
  const refreshed = new LiveCollector();
  await refreshed.ready();
  expect(refreshed.status().observationCount).toBe(1);
  expect(await deliverOld()).toMatchObject({ error: 'SESSION_OWNER_CHANGED' });
  expect(refreshed.status().observationCount).toBe(1);
});

it('keeps the acknowledged export and blocks refreshed capture after a quota rejection', async () => {
  await import('../entrypoints/background');
  const { LiveCollector } = await import('../entrypoints/collector.content');
  const page = new LiveCollector();
  await page.ready();
  const internal = page as unknown as { state: string; sessionId: string; startedAt: number;
    ratios: WeakMap<Element, number>; process: (article: Element) => void };
  internal.state = 'CAPTURING';
  internal.sessionId = 'quota-session';
  internal.startedAt = Date.now() - 1000;
  const article = document.createElement('article');
  internal.ratios.set(article, 1);
  article.dataset.postId = '1';
  internal.process(article);
  await vi.waitFor(() => expect(page.status().observationCount).toBe(1));
  mocks.set.mockImplementationOnce(async () => { throw new Error('quota'); });
  article.dataset.postId = '2';
  internal.process(article);
  await vi.waitFor(() => expect(page.status()).toMatchObject({ state: 'ERROR', hardStopCode: 'RETENTION_FAILURE', observationCount: 1 }));
  setDocumentStart(2000);
  const refreshed = new LiveCollector();
  await refreshed.ready();
  expect(refreshed.status()).toMatchObject({ state: 'ERROR', hardStopCode: 'RETENTION_FAILURE', observationCount: 1 });
  const exported = await refreshed.exportPacket();
  expect(exported.ok).toBe(true);
  const json = Array.from({ length: exported.export!.chunkCount }, (_, index) => refreshed.exportChunk(exported.export!.id, index).chunk).join('');
  expect((JSON.parse(json) as { observations: unknown[] }).observations).toHaveLength(1);
});

it('marks an enrichment as pending without changing the saved export or count', async () => {
  await import('../entrypoints/background');
  const { LiveCollector } = await import('../entrypoints/collector.content');
  const page = new LiveCollector();
  await page.ready();
  const internal = page as unknown as { state: string; sessionId: string; startedAt: number;
    ratios: WeakMap<Element, number>; process: (article: Element) => void };
  internal.state = 'CAPTURING';
  internal.sessionId = 'enrichment-session';
  internal.startedAt = Date.now() - 1000;
  const article = document.createElement('article');
  article.dataset.postId = '1';
  internal.ratios.set(article, 1);
  internal.process(article);
  await vi.waitFor(() => expect(page.status().observationCount).toBe(1));
  mocks.sendRuntime.mockImplementation((message: { type: string }) => message.type === 'XFI_SESSION_WRITE'
    ? new Promise(() => undefined)
    : mocks.backgroundListener!(message, { id: 'test-extension', tab: { id: 7 } }));
  article.dataset.visibleText = 'A much longer visible post after hydration';
  internal.process(article);
  expect(page.status()).toMatchObject({ observationCount: 1, pendingObservationCount: 0, pendingChanges: true });
  const exported = await page.exportPacket();
  const json = Array.from({ length: exported.export!.chunkCount }, (_, index) => page.exportChunk(exported.export!.id, index).chunk).join('');
  expect((JSON.parse(json) as { observations: Array<{ visible_text: string }> }).observations[0]!.visible_text).toBe('Visible 1');
  setDocumentStart(2000);
  const refreshed = new LiveCollector();
  await refreshed.ready();
  expect(refreshed.status().observationCount).toBe(1);
});
