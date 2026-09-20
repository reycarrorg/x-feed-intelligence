import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('wxt/browser', () => ({ browser: { runtime: { id: 'test-extension', onMessage: { addListener: vi.fn() } } } }));
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
    expect(collector.status()).toMatchObject({ state: 'LIMIT_REACHED', hardStopCode: 'AUTO_SCROLL_NO_PROGRESS', autoScroll: false });
    vi.useRealTimers();
  });
});
