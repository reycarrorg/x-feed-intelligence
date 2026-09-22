import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('wxt/browser', () => ({ browser: { runtime: { id: 'test-extension', sendMessage: vi.fn(async (message: { type: string }) =>
  message.type === 'XFI_SESSION_READ' ? { snapshot: null } : { ok: true }), onMessage: { addListener: vi.fn() } } } }));
vi.mock('../lib/parser', () => ({ SELECTORS: { post: 'article' }, viewportVisibilityRatio: () => 1, parseCard: vi.fn() }));

beforeEach(() => {
  vi.stubGlobal('defineContentScript', (definition: unknown) => definition);
  vi.stubGlobal('location', new URL('https://x.com/home'));
  vi.useFakeTimers();
  document.body.innerHTML = '';
  Object.defineProperty(document, 'visibilityState', { configurable: true, value: 'visible' });
  Object.defineProperty(window, 'scrollY', { configurable: true, value: 0 });
  Object.defineProperty(window, 'innerHeight', { configurable: true, value: 900 });
});

describe('opt-in careful auto-scroll', () => {
  it('requires active visible capture and obeys explicit stop', async () => {
    const { LiveCollector } = await import('../entrypoints/collector.content');
    const collector = new LiveCollector();
    expect(collector.startScroll().ok).toBe(false);
    const internal = collector as unknown as { state: string };
    internal.state = 'CAPTURING';
    expect(collector.startScroll().ok).toBe(true);
    expect(collector.status().autoScroll).toBe(true);
    expect(collector.stopScroll().ok).toBe(true);
    expect(collector.status().autoScroll).toBe(false);
    vi.useRealTimers();
  });

  it('caps each step and hard-stops capture after no new-card progress', async () => {
    const { LiveCollector } = await import('../entrypoints/collector.content');
    const collector = new LiveCollector();
    const internal = collector as unknown as { state: string; lastDomChange: number; lastScrollProgress: number; scrollTick: () => void };
    internal.state = 'CAPTURING';
    const scroll = vi.spyOn(window, 'scrollBy').mockImplementation(() => {});
    collector.startScroll();
    internal.lastDomChange = Date.now() - 1000;
    internal.scrollTick();
    expect(scroll).toHaveBeenCalledWith({ top: 108, behavior: 'instant' });
    internal.lastScrollProgress = Date.now() - 21_000;
    internal.scrollTick();
    await vi.waitFor(() => expect(collector.status()).toMatchObject({ state: 'LIMIT_REACHED', hardStopCode: 'AUTO_SCROLL_NO_PROGRESS', autoScroll: false }));
    vi.useRealTimers();
  });

  it('advances a bounded nested feed scroller instead of assuming window scrolling', async () => {
    const { LiveCollector } = await import('../entrypoints/collector.content');
    const feed = document.createElement('main');
    feed.style.overflowY = 'auto';
    Object.defineProperties(feed, { clientHeight: { configurable: true, value: 500 }, clientWidth: { configurable: true, value: 600 }, scrollHeight: { configurable: true, value: 2000 } });
    Object.defineProperty(feed, 'scrollBy', { configurable: true, value: ({ top }: { top: number }) => { feed.scrollTop += top; } });
    feed.append(document.createElement('article'));
    document.body.append(feed);
    const collector = new LiveCollector(); await collector.ready();
    const internal = collector as unknown as { state: string; stopCode: string | null; lastDomChange: number; scrollTick: () => void };
    internal.state = 'CAPTURING';
    collector.startScroll();
    internal.lastDomChange = Date.now() - 1000;
    internal.scrollTick();
    expect(feed.scrollTop).toBe(108);
    expect(collector.status().autoScroll).toBe(true);
    vi.useRealTimers();
  });

  it('does not use a direct scroll-position fallback when a nested feed lacks scrollBy', async () => {
    const { LiveCollector } = await import('../entrypoints/collector.content');
    const feed = document.createElement('main');
    feed.style.overflowY = 'auto';
    Object.defineProperties(feed, {
      clientHeight: { configurable: true, value: 500 },
      clientWidth: { configurable: true, value: 600 },
      scrollHeight: { configurable: true, value: 2000 },
      scrollBy: { configurable: true, value: undefined },
    });
    feed.append(document.createElement('article')); document.body.append(feed);
    const collector = new LiveCollector(); await collector.ready();
    const internal = collector as unknown as { state: string; lastDomChange: number; scrollTick: () => void };
    internal.state = 'CAPTURING'; collector.startScroll(); internal.lastDomChange = Date.now() - 1000;
    internal.scrollTick();
    expect(feed.scrollTop).toBe(0);
    expect(collector.status()).toMatchObject({ autoScroll: true, scrollPauseReason: 'NO_SCROLL_MOVEMENT' });
    vi.useRealTimers();
  });

  it('does not scroll a larger unrelated pane when visible post cards belong to a smaller feed', async () => {
    const { LiveCollector } = await import('../entrypoints/collector.content');
    const drawer = document.createElement('main');
    const feed = document.createElement('main');
    for (const [element, height, width] of [[drawer, 900, 1000], [feed, 500, 600]] as const) {
      element.style.overflowY = 'auto';
      Object.defineProperties(element, { clientHeight: { configurable: true, value: height }, clientWidth: { configurable: true, value: width }, scrollHeight: { configurable: true, value: 3000 } });
      Object.defineProperty(element, 'scrollBy', { configurable: true, value: ({ top }: { top: number }) => { element.scrollTop += top; } });
      document.body.append(element);
    }
    feed.append(document.createElement('article'));
    const collector = new LiveCollector(); await collector.ready();
    const internal = collector as unknown as { state: string; lastDomChange: number; scrollTick: () => void };
    internal.state = 'CAPTURING';
    collector.startScroll();
    internal.lastDomChange = Date.now() - 1000;
    internal.scrollTick();
    expect(feed.scrollTop).toBe(108);
    expect(drawer.scrollTop).toBe(0);
    vi.useRealTimers();
  });

  it('prefers the innermost eligible scroll ancestor of a visible post', async () => {
    const { LiveCollector } = await import('../entrypoints/collector.content');
    const outer = document.createElement('main');
    const inner = document.createElement('div');
    inner.setAttribute('role', 'main');
    for (const [element, height, width] of [[outer, 800, 900], [inner, 500, 600]] as const) {
      element.style.overflowY = 'auto';
      Object.defineProperties(element, { clientHeight: { configurable: true, value: height }, clientWidth: { configurable: true, value: width }, scrollHeight: { configurable: true, value: 3000 } });
      Object.defineProperty(element, 'scrollBy', { configurable: true, value: ({ top }: { top: number }) => { element.scrollTop += top; } });
    }
    inner.append(document.createElement('article'));
    outer.append(inner); document.body.append(outer);
    const collector = new LiveCollector();
    const internal = collector as unknown as { state: string; lastDomChange: number; scrollTick: () => void };
    internal.state = 'CAPTURING'; collector.startScroll(); internal.lastDomChange = Date.now() - 1000; internal.scrollTick();
    expect(inner.scrollTop).toBe(108); expect(outer.scrollTop).toBe(0);
    vi.useRealTimers();
  });

  it('stops a physically moving blank nested feed after the no-new-card interval', async () => {
    const { LiveCollector } = await import('../entrypoints/collector.content');
    const feed = document.createElement('main'); feed.style.overflowY = 'auto';
    Object.defineProperties(feed, { clientHeight: { configurable: true, value: 500 }, clientWidth: { configurable: true, value: 600 }, scrollHeight: { configurable: true, value: 3000 } });
    Object.defineProperty(feed, 'scrollBy', { configurable: true, value: ({ top }: { top: number }) => { feed.scrollTop += top; } });
    feed.append(document.createElement('article')); document.body.append(feed);
    const collector = new LiveCollector(); await collector.ready();
    const internal = collector as unknown as { state: string; lastDomChange: number; scrollTick: () => void };
    internal.state = 'CAPTURING'; collector.startScroll(); internal.lastDomChange = Date.now() - 1000; internal.scrollTick();
    expect(feed.scrollTop).toBe(108);
    vi.advanceTimersByTime(21_000); internal.lastDomChange = Date.now() - 1000; internal.scrollTick();
    expect(internal).toMatchObject({ state: 'LIMIT_REACHED', stopCode: 'AUTO_SCROLL_NO_PROGRESS' });
    vi.useRealTimers();
  });
});
