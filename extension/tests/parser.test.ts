import { beforeEach, describe, expect, it } from 'vitest';
import { parseCard, statusIdentity, viewportVisibilityRatio } from '../lib/parser';

function markVisible(root: Element): void {
  for (const element of [root, ...Array.from(root.querySelectorAll('*'))]) {
    Object.defineProperty(element, 'getClientRects', {
      configurable: true,
      value: () => [{ top: 10, left: 10, right: 310, bottom: 110, width: 300, height: 100 }],
    });
  }
}

describe('visible X card parser', () => {
  beforeEach(() => {
    document.body.innerHTML = '';
    Object.defineProperty(window, 'innerHeight', { configurable: true, value: 900 });
    Object.defineProperty(window, 'innerWidth', { configurable: true, value: 1200 });
  });

  it('extracts only visible card fields and canonicalizes the status identity', () => {
    document.body.innerHTML = `
      <article data-testid="tweet">
        <div data-testid="User-Name"><a href="/Example"><span>Example Author</span></a><span>@Example</span></div>
        <a href="/Example/status/1234567890123456789"><time datetime="2030-01-02T03:04:05Z">1m</time></a>
        <div data-testid="tweetText"><span>Measured benchmark with GitHub documentation and a stated limitation.</span></div>
        <div data-testid="tweetPhoto"><img alt="Synthetic chart" /></div>
      </article>`;
    const article = document.querySelector('article')!;
    markVisible(article);
    const parsed = parseCard(article);
    expect(parsed.platformPostId).toBe('1234567890123456789');
    expect(parsed.canonicalPermalink).toBe(`https://x.com/Example/status/${'1234567890123456789'}`);
    expect(parsed.handle).toBe('Example');
    expect(parsed.displayName).toBe('Example Author');
    expect(parsed.visibleText).toBe('Measured benchmark with GitHub documentation and a stated limitation.');
    expect(parsed.media).toEqual([{ kind: 'image', altText: 'Synthetic chart' }]);
    expect(parsed.promotion).toBe('organic');
  });

  it('recognizes a visible promoted label', () => {
    document.body.innerHTML = `
      <article data-testid="tweet">
        <div data-testid="User-Name"><span>Brand @brand</span></div>
        <a href="/brand/status/9876543210987654321"><time>now</time></a>
        <span data-testid="placementTracking">Promoted</span>
        <div data-testid="tweetText">Offer text</div>
      </article>`;
    const article = document.querySelector('article')!;
    markVisible(article);
    const parsed = parseCard(article);
    expect(parsed.promotion).toBe('promoted');
    expect(parsed.promotionEvidence).toBe('visible_label');
    expect(parsed.preview.grade).toBe('F');
  });

  it('does not accept unrelated or malformed status links as a post identity', () => {
    document.body.innerHTML = '<article><a href="https://evil.invalid/user/status/123">link</a></article>';
    expect(statusIdentity(document.querySelector('article')!)).toEqual({ id: null, permalink: null });
  });

  it('computes current viewport area instead of trusting a stale observer entry', () => {
    document.body.innerHTML = '<article>partly visible</article>';
    const article = document.querySelector('article')!;
    markVisible(article);
    Object.defineProperty(article, 'getBoundingClientRect', {
      configurable: true,
      value: () => ({ top: -50, left: 0, right: 200, bottom: 50, width: 200, height: 100 }),
    });
    expect(viewportVisibilityRatio(article)).toBe(0.5);
  });
});
