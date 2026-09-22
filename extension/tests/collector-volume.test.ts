import { webcrypto } from 'node:crypto';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { LIMITS } from '../lib/contracts';

const runtime = vi.hoisted(() => ({ sendMessage: vi.fn(async (message: { type: string }) =>
  message.type === 'XFI_SESSION_READ' ? { snapshot: null } : { ok: true }) }));

vi.mock('wxt/browser', () => ({ browser: { runtime: { id: 'test-extension', sendMessage: runtime.sendMessage, onMessage: { addListener: vi.fn() } } } }));
vi.mock('../lib/parser', () => ({
  SELECTORS: { post: 'article' },
  viewportVisibilityRatio: () => 1,
  parseCard: (article: HTMLElement) => ({
    platformPostId: article.dataset.postId || '10001', canonicalPermalink: `https://x.com/example/status/${article.dataset.postId || '10001'}`,
    handle: 'example', displayName: 'Example', displayedTimestamp: null,
    visibleText: article.dataset.visibleText || `A further visible card. ${'Evidence '.repeat(70)}`, promotion: 'organic', promotionEvidence: 'none',
    media: [], quote: null, outboundLinks: [], uncertaintyCodes: [], preview: { grade: 'B', reasons: ['synthetic'] },
  }),
}));

beforeEach(() => {
  vi.stubGlobal('defineContentScript', (definition: unknown) => definition);
  vi.stubGlobal('crypto', webcrypto);
  vi.stubGlobal('location', new URL('https://x.com/home'));
  runtime.sendMessage.mockImplementation(async (message: { type: string }) =>
    message.type === 'XFI_SESSION_READ' ? { snapshot: null } : { ok: true });
  Object.defineProperty(document, 'visibilityState', { configurable: true, value: 'visible' });
  document.body.innerHTML = '';
});

describe('large manual capture export', () => {
  it('increments the live visible-card and promotion counters when a card is accepted', async () => {
    const { LiveCollector } = await import('../entrypoints/collector.content');
    const collector = new LiveCollector();
    const internal = collector as unknown as {
      state: string; sessionId: string; startedAt: number;
      ratios: WeakMap<Element, number>; process: (article: Element) => void;
    };
    internal.state = 'CAPTURING';
    internal.sessionId = 'synthetic-count-session';
    internal.startedAt = Date.now() - 1000;
    const article = document.createElement('article');
    internal.ratios.set(article, 1);
    internal.process(article);
    expect(collector.status()).toMatchObject({ observationCount: 0, pendingObservationCount: 1 });
    await vi.waitFor(() => expect(collector.status()).toMatchObject({ observationCount: 1, pendingObservationCount: 0, organicCount: 1, promotedCount: 0, ambiguousCount: 0 }));
  });

  it('automatically rolls over before the refresh-safe cap and continues into a cumulative next part', async () => {
    const { LiveCollector } = await import('../entrypoints/collector.content');
    const collector = new LiveCollector();
    await collector.ready();
    await collector.start();
    const internal = collector as unknown as {
      sessionId: string;
      ratios: WeakMap<Element, number>; process: (article: Element) => void;
    };
    const firstSessionId = internal.sessionId!;
    const article = document.createElement('article');
    internal.ratios.set(article, 1);
    for (let index = 0; index < LIMITS.maxCandidates; index += 1) {
      article.dataset.postId = String(index + 1);
      internal.process(article);
    }
    await vi.waitFor(() => expect(collector.status()).toMatchObject({ state: 'ROLLING_OVER', hardStopCode: null }));
    const firstPartCount = collector.status().observationCount;
    expect(firstPartCount).toBeGreaterThan(0);
    expect(firstPartCount).toBeLessThan(10_000);
    expect(collector.status().totalObservationCount).toBe(firstPartCount);

    const continued = await collector.completeRollover(firstSessionId);
    expect(continued.ok).toBe(true);
    expect(collector.status()).toMatchObject({ state: 'CAPTURING', observationCount: 0, totalObservationCount: firstPartCount, partNumber: 2 });
    article.dataset.postId = 'new-post-after-rollover';
    article.dataset.visibleText = 'A genuinely new post after the automatic part rollover.';
    (collector as unknown as { ratios: WeakMap<Element, number> }).ratios.set(article, 1);
    internal.process(article);
    await vi.waitFor(() => expect(collector.status()).toMatchObject({ observationCount: 1, totalObservationCount: firstPartCount + 1, partNumber: 2 }));
  });

  it('preserves the last saved content, then rolls the oversized update into a new part', async () => {
    const { LiveCollector } = await import('../entrypoints/collector.content');
    const collector = new LiveCollector();
    await collector.ready();
    await collector.start();
    const internal = collector as unknown as { state: string; sessionId: string; startedAt: number;
      ratios: WeakMap<Element, number>; process: (article: Element) => void };
    const firstSessionId = internal.sessionId!;
    const article = document.createElement('article');
    internal.ratios.set(article, 1);
    internal.process(article);
    await vi.waitFor(() => expect(collector.status().observationCount).toBe(1));
    article.dataset.visibleText = 'x'.repeat(LIMITS.maxRefreshRecoveryBytes);
    internal.process(article);
    await vi.waitFor(() => expect(collector.status()).toMatchObject({ state: 'ROLLING_OVER', hardStopCode: null, observationCount: 1 }));
    const packet = await collector.exportPacket();
    expect(packet.ok).toBe(true);
    const json = Array.from({ length: packet.export!.chunkCount }, (_, index) => collector.exportChunk(packet.export!.id, index).chunk).join('');
    expect((JSON.parse(json) as { observations: Array<{ visible_text: string }> }).observations[0]!.visible_text.length).toBeLessThan(1000);
    expect(collector.releaseExport(packet.export!.id).ok).toBe(true);
    await collector.completeRollover(firstSessionId);
    expect(collector.status()).toMatchObject({ state: 'CAPTURING', observationCount: 0, totalObservationCount: 1, partNumber: 2 });
  });

  it('keeps the saved part available when its automatic download fails', async () => {
    runtime.sendMessage.mockImplementation(async (message: { type: string }) => {
      if (message.type === 'XFI_SESSION_READ') return { snapshot: null };
      if (message.type === 'XFI_AUTO_SAVE_EXPORT') return { ok: false, error: 'DOWNLOAD_INTERRUPTED' };
      return { ok: true };
    });
    const { LiveCollector } = await import('../entrypoints/collector.content');
    const collector = new LiveCollector();
    await collector.ready();
    await collector.start();
    const internal = collector as unknown as { sessionId: string; ratios: WeakMap<Element, number>; process: (article: Element) => void };
    const sessionId = internal.sessionId;
    const article = document.createElement('article');
    internal.ratios.set(article, 1);
    internal.process(article);
    await vi.waitFor(() => expect(collector.status().observationCount).toBe(1));
    article.dataset.visibleText = 'x'.repeat(LIMITS.maxRefreshRecoveryBytes);
    internal.process(article);
    await vi.waitFor(() => expect(collector.status()).toMatchObject({ state: 'ERROR', observationCount: 1, totalObservationCount: 1, partNumber: 1 }));
    expect(collector.status().hardStopCode).toBe('DOWNLOAD_INTERRUPTED');
    const retainedPacket = await collector.exportPacket();
    expect(retainedPacket.ok).toBe(true);
    expect(sessionId).toBeTruthy();
  });
});
