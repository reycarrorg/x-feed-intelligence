/**
 * Visible X DOM parser.
 *
 * Portions of the selector, author, timestamp, status-ID, and quoted-card logic
 * are adapted from XClipper 2.8.2 by Ali Zendegani, commit
 * 3f7c6caa2e6f02bf37d140b989cbbdf4485275a5, under the PolyForm
 * Noncommercial License 1.0.0. Required attribution is retained in
 * THIRD_PARTY_NOTICES.md and extension/UPSTREAM_NOTICES.md.
 */

import { containsPromptInjection, previewGrade } from './classifier';
import type { PromotionStatus } from './contracts';

export const SELECTORS = Object.freeze({
  post: 'article[data-testid="tweet"], article[role="article"]',
  tweetText: '[data-testid="tweetText"]',
  userName: '[data-testid="User-Name"]',
  photo: '[data-testid="tweetPhoto"]',
});

export interface ParsedCard {
  platformPostId: string | null;
  canonicalPermalink: string | null;
  visibleText: string | null;
  displayedTimestamp: string | null;
  displayName: string | null;
  handle: string | null;
  promotion: PromotionStatus;
  promotionEvidence: 'visible_label' | 'delayed_label' | 'layout_marker' | 'manual_review' | 'none';
  media: Array<{ kind: 'image' | 'video' | 'animated_image' | 'link_card' | 'unknown'; altText: string | null }>;
  uncertaintyCodes: string[];
  preview: ReturnType<typeof previewGrade>;
}

export function isElementVisible(element: Element, root: Element): boolean {
  for (let current: Element | null = element; current; current = current.parentElement) {
    const style = getComputedStyle(current);
    if (current.hasAttribute('hidden') || current.getAttribute('aria-hidden') === 'true' || style.display === 'none' || style.visibility === 'hidden' || (style.opacity !== '' && Number(style.opacity) === 0)) return false;
    if (current === root) break;
  }
  const rectangles = element.getClientRects();
  if (!rectangles.length) return false;
  return Array.from(rectangles).some((rect) => rect.width > 0 && rect.height > 0 && rect.bottom > 0 && rect.right > 0 && rect.top < innerHeight && rect.left < innerWidth);
}

export function viewportVisibilityRatio(element: Element): number {
  if (!isElementVisible(element, element)) return 0;
  const rect = element.getBoundingClientRect();
  if (rect.width <= 0 || rect.height <= 0) return 0;
  const visibleWidth = Math.max(0, Math.min(rect.right, innerWidth) - Math.max(rect.left, 0));
  const visibleHeight = Math.max(0, Math.min(rect.bottom, innerHeight) - Math.max(rect.top, 0));
  return Math.max(0, Math.min(1, (visibleWidth * visibleHeight) / (rect.width * rect.height)));
}

export function visibleText(element: Element | null, root: Element): string | null {
  if (!element || !isElementVisible(element, root)) return null;
  const chunks: string[] = [];
  const walker = document.createTreeWalker(element, NodeFilter.SHOW_TEXT);
  for (let node = walker.nextNode(); node; node = walker.nextNode()) {
    const parent = node.parentElement;
    if (node.nodeValue?.trim() && parent && isElementVisible(parent, root)) chunks.push(node.nodeValue.trim());
  }
  return chunks.join(' ').replace(/\s+/g, ' ').trim() || null;
}

export function statusIdentity(article: Element): { id: string | null; permalink: string | null } {
  const candidates = article.querySelectorAll<HTMLAnchorElement>('a[href*="/status/"]');
  for (const anchor of candidates) {
    const href = anchor.getAttribute('href') || '';
    let parsed: URL;
    try {
      parsed = new URL(href, 'https://x.com');
    } catch {
      continue;
    }
    if (parsed.origin !== 'https://x.com') continue;
    const match = parsed.pathname.match(/^\/([A-Za-z0-9_]{1,15})\/status\/(\d+)(?:\/|$)/);
    if (!match) continue;
    const [, handle, id] = match;
    if (!handle || !id) continue;
    return { id, permalink: `https://x.com/${handle}/status/${id}` };
  }
  return { id: null, permalink: null };
}

export function parseAuthor(article: Element): { displayName: string | null; handle: string | null } {
  const container = article.querySelector(SELECTORS.userName);
  if (!container) return { displayName: null, handle: null };
  const compact = (container.textContent || '').replace(/\s+/g, ' ').trim();
  const handleMatch = compact.match(/@([A-Za-z0-9_]{1,15})/);
  const handle = handleMatch?.[1] || Array.from(container.querySelectorAll<HTMLAnchorElement>('a[href]'))
    .map((anchor) => anchor.getAttribute('href')?.match(/^\/([A-Za-z0-9_]{1,15})$/)?.[1])
    .find(Boolean) || null;
  const displayName = handleMatch && compact.indexOf(handleMatch[0]) > 0
    ? compact.slice(0, compact.indexOf(handleMatch[0])).trim() || null
    : Array.from(container.querySelectorAll('a')).map((anchor) => anchor.textContent?.trim()).find((value) => value && !value.startsWith('@')) || null;
  return { displayName, handle };
}

function parsePromotion(article: Element): { status: PromotionStatus; evidence: ParsedCard['promotionEvidence'] } {
  const labelCandidates = Array.from(article.querySelectorAll('[data-testid="placementTracking"], [aria-label], span'));
  for (const element of labelCandidates) {
    if (!isElementVisible(element, article)) continue;
    const value = `${element.getAttribute('aria-label') || ''} ${element.textContent || ''}`.replace(/\s+/g, ' ').trim();
    if (/^(?:promoted|ad|sponsored)(?:\s|$)/i.test(value) || /\bpromoted by\b/i.test(value)) return { status: 'promoted', evidence: 'visible_label' };
  }
  return { status: 'organic', evidence: 'none' };
}

function parseMedia(article: Element): ParsedCard['media'] {
  const media: ParsedCard['media'] = [];
  const seen = new Set<Element>();
  const push = (element: Element, kind: ParsedCard['media'][number]['kind']) => {
    if (seen.has(element) || !isElementVisible(element, article)) return;
    seen.add(element);
    const image = element instanceof HTMLImageElement ? element : element.querySelector('img');
    media.push({ kind, altText: image?.getAttribute('alt')?.trim() || null });
  };
  article.querySelectorAll(SELECTORS.photo).forEach((element) => push(element, 'image'));
  article.querySelectorAll('video').forEach((element) => push(element, 'video'));
  article.querySelectorAll('[data-testid="card.wrapper"]').forEach((element) => push(element, 'link_card'));
  return media.slice(0, 16);
}

export function parseCard(article: Element): ParsedCard {
  const identity = statusIdentity(article);
  const author = parseAuthor(article);
  const textElements = article.querySelectorAll(SELECTORS.tweetText);
  const text = visibleText(textElements[0] || null, article);
  const timestamp = article.querySelector('time');
  const promotion = parsePromotion(article);
  const uncertaintyCodes: string[] = [];
  if (!identity.id) uncertaintyCodes.push('MISSING_PLATFORM_ID');
  if (!author.handle) uncertaintyCodes.push('MISSING_AUTHOR_HANDLE');
  if (!text && !article.querySelector('img, video')) uncertaintyCodes.push('MISSING_VISIBLE_CONTENT');
  if (textElements.length > 1) uncertaintyCodes.push('EMBEDDED_QUOTE_REVIEW_REQUIRED');
  if (containsPromptInjection(text || '')) uncertaintyCodes.push('PROMPT_INJECTION');
  return {
    platformPostId: identity.id,
    canonicalPermalink: identity.permalink,
    visibleText: text,
    displayedTimestamp: timestamp?.getAttribute('datetime') || timestamp?.textContent?.trim() || null,
    ...author,
    promotion: promotion.status,
    promotionEvidence: promotion.evidence,
    media: parseMedia(article),
    uncertaintyCodes,
    preview: previewGrade(text, promotion.status === 'promoted'),
  };
}
