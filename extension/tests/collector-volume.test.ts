import { webcrypto } from 'node:crypto';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { LIMITS } from '../lib/contracts';

vi.mock('wxt/browser', () => ({ browser: { runtime: { id: 'test-extension', onMessage: { addListener: vi.fn() } } } }));
vi.mock('../lib/parser', () => ({
  SELECTORS: { post: 'article' },
  viewportVisibilityRatio: () => 1,
  parseCard: (article: HTMLElement) => ({
    platformPostId: article.dataset.postId || '10001', canonicalPermalink: `https://x.com/example/status/${article.dataset.postId || '10001'}`,
    handle: 'example', displayName: 'Example', displayedTimestamp: null,
    visibleText: `A further visible card. ${'Evidence '.repeat(70)}`, promotion: 'organic', promotionEvidence: 'none',
    media: [], quote: null, outboundLinks: [], uncertaintyCodes: [], preview: { grade: 'B', reasons: ['synthetic'] },
  }),
}));

beforeEach(() => {
  vi.stubGlobal('defineContentScript', (definition: unknown) => definition);
  vi.stubGlobal('crypto', webcrypto);
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
    expect(collector.status()).toMatchObject({ observationCount: 1, organicCount: 1, promotedCount: 0, ambiguousCount: 0 });
  });

  it('chunks a large export and stops at the 15 MiB cap before 10,000 cards', async () => {
    const { LiveCollector } = await import('../entrypoints/collector.content');
    const collector = new LiveCollector();
    const internal = collector as unknown as {
      state: string; sessionId: string; startedAt: number;
      ratios: WeakMap<Element, number>; process: (article: Element) => void;
    };
    internal.state = 'CAPTURING';
    internal.sessionId = 'synthetic-volume-session';
    internal.startedAt = Date.now() - 1000;
    const article = document.createElement('article');
    internal.ratios.set(article, 1);
    for (let index = 0; index < LIMITS.maxCandidates; index += 1) {
      article.dataset.postId = String(index + 1);
      internal.process(article);
    }
    expect(collector.status()).toMatchObject({ state: 'LIMIT_REACHED', hardStopCode: 'PACKET_LIMIT' });
    expect(collector.status().observationCount).toBeGreaterThan(1000);
    expect(collector.status().observationCount).toBeLessThan(10_000);

    const exported = await collector.exportPacket();
    expect(exported.ok).toBe(true);
    expect(exported.export?.chunkCount).toBeGreaterThan(1);
    expect(exported.export?.totalBytes).toBeGreaterThan(5_242_880);
    const chunks = Array.from({ length: exported.export!.chunkCount }, (_, index) =>
      collector.exportChunk(exported.export!.id, index).chunk);
    expect(chunks.every((chunk) => typeof chunk === 'string' && chunk.length <= 262_144)).toBe(true);
    const json = chunks.join('');
    expect(new TextEncoder().encode(json).length).toBe(exported.export?.totalBytes);
    expect((JSON.parse(json) as { observations: unknown[] }).observations).toHaveLength(collector.status().observationCount);
    expect(collector.releaseExport(exported.export!.id).ok).toBe(true);
    expect(collector.exportChunk(exported.export!.id, 0).ok).toBe(false);

    article.dataset.postId = '10001';
    internal.process(article);
    expect(collector.status().observationCount).toBeLessThan(10_000);
  });
});
