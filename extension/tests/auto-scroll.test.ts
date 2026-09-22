import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('wxt/browser', () => ({ browser: { runtime: { id: 'test-extension', sendMessage: vi.fn(async (message: { type: string }) =>
  message.type === 'XFI_SESSION_READ' ? { snapshot: null } : { ok: true }), onMessage: { addListener: vi.fn() } } } }));
vi.mock('../lib/parser', () => ({ SELECTORS: { post: 'article' }, viewportVisibilityRatio: () => 1, parseCard: (article: HTMLElement) => ({
  platformPostId: article.dataset.postId || '10001', canonicalPermalink: `https://x.com/example/status/${article.dataset.postId || '10001'}`,
  handle: 'example', displayName: 'Example', displayedTimestamp: null, visibleText: 'A visible post for scroll coverage.',
  promotion: 'organic', promotionEvidence: 'none', media: [], quote: null, outboundLinks: [], uncertaintyCodes: [],
  preview: { grade: 'B', reasons: ['synthetic'] },
}) }));

beforeEach(() => {
  vi.stubGlobal('defineContentScript', (definition: unknown) => definition);
  vi.stubGlobal('location', new URL('https://x.com/home'));
  vi.useFakeTimers();
  document.body.innerHTML = '';
  Object.defineProperty(document, 'visibilityState', { configurable: true, value: 'visible' });
  Object.defineProperty(window, 'innerHeight', { configurable: true, value: 900 });
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

function scrollableFeed(): HTMLElement {
  const feed = document.createElement('main');
  feed.style.overflowY = 'auto';
  Object.defineProperties(feed, {
    clientHeight: { configurable: true, value: 500 },
    clientWidth: { configurable: true, value: 600 },
    scrollHeight: { configurable: true, value: 2000 },
  });
  feed.append(document.createElement('article'));
  document.body.append(feed);
  return feed;
}

describe('careful auto-scroll', () => {
  it('requires active visible capture and obeys explicit stop', async () => {
    const { LiveCollector } = await import('../entrypoints/collector.content');
    const collector = new LiveCollector();
    await collector.ready();
    expect(collector.startScroll().ok).toBe(false);
    await collector.start();
    expect(collector.startScroll().ok).toBe(true);
    expect(collector.status().autoScroll).toBe(true);
    expect(collector.stopScroll().ok).toBe(true);
    expect(collector.status()).toMatchObject({ autoScroll: false, state: 'CAPTURING' });
  });

  it('sets scrollTop on the visible feed container without synthesizing pointer input', async () => {
    const feed = scrollableFeed();
    const { LiveCollector } = await import('../entrypoints/collector.content');
    const collector = new LiveCollector();
    await collector.ready();
    const internal = collector as unknown as { lastDomChange: number; scrollTick: () => void };
    await collector.start();
    collector.startScroll();
    internal.lastDomChange = Date.now() - 1000;
    internal.scrollTick();
    expect(feed.scrollTop).toBeGreaterThan(0);
    expect(feed.scrollTop).toBeLessThanOrEqual(160);
    expect(collector.status()).toMatchObject({ state: 'CAPTURING', autoScroll: true, scrollPauseReason: 'NESTED_FEED_SCROLL' });
  });

  it('pauses only scrolling after trusted user input and keeps capture active', async () => {
    scrollableFeed();
    const { LiveCollector } = await import('../entrypoints/collector.content');
    const collector = new LiveCollector();
    await collector.ready();
    const internal = collector as unknown as { stopScrollOnInput: (event: Event) => void };
    await collector.start();
    collector.startScroll();
    const event = new Event('wheel');
    Object.defineProperty(event, 'isTrusted', { value: true });
    internal.stopScrollOnInput(event);
    expect(collector.status()).toMatchObject({ state: 'CAPTURING', autoScroll: false, scrollPauseReason: 'USER_INPUT' });
  });

  it('pauses scrolling after 30 seconds without progress but does not stop collection', async () => {
    scrollableFeed();
    const { LiveCollector } = await import('../entrypoints/collector.content');
    const collector = new LiveCollector();
    await collector.ready();
    const internal = collector as unknown as { lastScrollProgress: number; scrollTick: () => void };
    await collector.start();
    collector.startScroll();
    internal.lastScrollProgress = Date.now() - 30_001;
    internal.scrollTick();
    expect(collector.status()).toMatchObject({ state: 'CAPTURING', autoScroll: false, scrollPauseReason: 'AUTO_SCROLL_NO_PROGRESS' });
  });

});
