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
  media: Array<{ kind: 'image' | 'video' | 'animated_image' | 'link_card' | 'unknown'; altText: string | null; visibleDescription?: string | null }>;
  quote: { id: string | null; permalink: string | null; displayName: string | null; handle: string | null; text: string | null; media: ParsedCard['media'] } | null;
  outboundLinks: Array<{ url: string; title: string | null; description: string | null }>;
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

export function statusIdentity(article: Element, excluded: Element | null = null): { id: string | null; permalink: string | null } {
  const candidates = article.querySelectorAll<HTMLAnchorElement>('a[href*="/status/"]');
  for (const anchor of candidates) {
    if (excluded?.contains(anchor)) continue;
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

export function parseAuthor(article: Element, excluded: Element | null = null): { displayName: string | null; handle: string | null } {
  const container = Array.from(article.querySelectorAll(SELECTORS.userName)).find((element) => !excluded?.contains(element));
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

function parsePromotion(article: Element, excluded: Element | null = null): { status: PromotionStatus; evidence: ParsedCard['promotionEvidence'] } {
  const labelCandidates = Array.from(article.querySelectorAll('[data-testid="placementTracking"], [aria-label], span'));
  for (const element of labelCandidates) {
    if (excluded?.contains(element)) continue;
    if (!isElementVisible(element, article)) continue;
    const value = `${element.getAttribute('aria-label') || ''} ${element.textContent || ''}`.replace(/\s+/g, ' ').trim();
    if (/^(?:promoted|ad|sponsored)(?:\s|$)/i.test(value) || /\bpromoted by\b/i.test(value)) return { status: 'promoted', evidence: 'visible_label' };
  }
  return { status: 'organic', evidence: 'none' };
}

function parseMedia(article: Element, excluded: Element | null = null): ParsedCard['media'] {
  const media: ParsedCard['media'] = [];
  const seen = new Set<Element>();
  const push = (element: Element, kind: ParsedCard['media'][number]['kind']) => {
    if (seen.has(element) || excluded?.contains(element) || !isElementVisible(element, article)) return;
    seen.add(element);
    const image = element instanceof HTMLImageElement ? element : element.querySelector('img');
    media.push({ kind, altText: image?.getAttribute('alt')?.trim() || null });
  };
  article.querySelectorAll(SELECTORS.photo).forEach((element) => push(element, 'image'));
  article.querySelectorAll('video').forEach((element) => push(element, 'video'));
  article.querySelectorAll('[data-testid="card.wrapper"]').forEach((element) => push(element, 'link_card'));
  return media.slice(0, 16);
}

function safeOutbound(raw: string | null): string | null {
  if (!raw) return null;
  try {
    const url = new URL(raw, location.origin);
    if (url.protocol !== 'https:' || url.username || url.password || ['x.com', 'twitter.com', 't.co'].includes(url.hostname)) return null;
    url.hash = '';
    return url.toString().slice(0, 2048);
  } catch { return null; }
}

function parseOutboundLinks(article: Element, quote: Element | null): ParsedCard['outboundLinks'] {
  const links: ParsedCard['outboundLinks'] = [];
  const seen = new Set<string>();
  article.querySelectorAll<HTMLAnchorElement>('a[href]').forEach((anchor) => {
    if (quote?.contains(anchor) || !isElementVisible(anchor, article)) return;
    const url = safeOutbound(anchor.getAttribute('href'));
    if (!url || seen.has(url) || links.length >= 16) return;
    seen.add(url);
    const card = anchor.closest('[data-testid="card.wrapper"]');
    const title = card?.querySelector('[data-testid="cardTitle"]') || card?.querySelector('h2, h3');
    const description = card?.querySelector('[data-testid="cardDescription"]');
    links.push({ url, title: visibleText(title || null, article)?.slice(0, 512) || null,
      description: visibleText(description || null, article)?.slice(0, 2048) || null });
  });
  return links;
}

export function parseCard(article: Element): ParsedCard {
  const quoteRoot = article.querySelector('[data-testid="quoteTweet"], [data-testid="quotedTweet"]');
  const own = (selector: string): Element | null => Array.from(article.querySelectorAll(selector)).find((element) => !quoteRoot?.contains(element)) || null;
  const identity = statusIdentity(article, quoteRoot);
  const author = parseAuthor(article, quoteRoot);
  const textElements = Array.from(article.querySelectorAll(SELECTORS.tweetText)).filter((element) => !quoteRoot?.contains(element));
  const text = visibleText(textElements[0] || null, article);
  const timestamp = own('time');
  const promotion = parsePromotion(article, quoteRoot);
  const quote = quoteRoot && isElementVisible(quoteRoot, article) ? {
    ...statusIdentity(quoteRoot), ...parseAuthor(quoteRoot),
    text: visibleText(quoteRoot.querySelector(SELECTORS.tweetText), article), media: parseMedia(quoteRoot),
  } : null;
  const outboundLinks = parseOutboundLinks(article, quoteRoot);
  const uncertaintyCodes: string[] = [];
  if (!identity.id) uncertaintyCodes.push('MISSING_PLATFORM_ID');
  if (!author.handle) uncertaintyCodes.push('MISSING_AUTHOR_HANDLE');
  if (!text) uncertaintyCodes.push('EMPTY_VISIBLE_BODY');
  if (!text && !article.querySelector('img, video')) uncertaintyCodes.push('MISSING_VISIBLE_CONTENT');
  if (quoteRoot && (!quote?.id || !quote?.handle || !quote?.text)) uncertaintyCodes.push('QUOTE_NEEDS_CONTEXT');
  if (article.querySelector('[data-testid="card.wrapper"]') && !outboundLinks.length) uncertaintyCodes.push('LINK_DESTINATION_UNRESOLVED');
  if (parseMedia(article, quoteRoot).some((item) => item.kind !== 'link_card' && (!item.altText || /^(?:image|photo|video|gif|media)$/i.test(item.altText)))) uncertaintyCodes.push('MEDIA_CONTEXT_REQUIRED');
  if (text && /(?:…|\.\.\.)\s*$/.test(text)) uncertaintyCodes.push('POSSIBLY_TRUNCATED_TEXT');
  if (containsPromptInjection(`${text || ''} ${quote?.text || ''}`)) uncertaintyCodes.push('PROMPT_INJECTION');
  return {
    platformPostId: identity.id,
    canonicalPermalink: identity.permalink,
    visibleText: text,
    displayedTimestamp: timestamp?.getAttribute('datetime') || timestamp?.textContent?.trim() || null,
    ...author,
    promotion: promotion.status,
    promotionEvidence: promotion.evidence,
    media: parseMedia(article, quoteRoot),
    quote,
    outboundLinks,
    uncertaintyCodes,
    preview: previewGrade(text, promotion.status === 'promoted'),
  };
}
