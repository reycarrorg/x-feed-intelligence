import { browser } from 'wxt/browser';
import { COLLECTOR_VERSION, EXACT_ORIGIN, LIMITS, PARSER_VERSION, type CollectorCommand, type CollectorResponse, type CollectorStatus, type LifecycleState } from '../lib/contracts';
import { parseCard, SELECTORS, viewportVisibilityRatio } from '../lib/parser';

const HARD_STOPS = new Set([
  'LOGIN_SURFACE', 'SIGN_OUT_STATE', 'ACCOUNT_LOCK', 'CAPTCHA_OR_TURNSTILE',
  'VERIFICATION_CHALLENGE', 'UNUSUAL_ACTIVITY', 'CONSENT_SURFACE', 'RATE_LIMIT',
  'WRONG_ORIGIN', 'IFRAME_BOUNDARY', 'PERMISSION_DRIFT', 'PARSER_VERSION_MISMATCH',
  'UNKNOWN_TOPOLOGY', 'AMBIGUITY_LIMIT', 'QUEUE_LIMIT', 'DURATION_LIMIT',
  'PACKET_LIMIT', 'DISK_OR_MEMORY_LIMIT', 'RETENTION_FAILURE', 'SCHEMA_MISMATCH',
  'EXCLUDED_PERMISSION_REQUEST', 'ACCOUNT_ACTION_REQUEST', 'INJECTION_CONTENT',
]);

interface Observation extends Record<string, unknown> {
  observation_id: string;
  session_id: string;
  appearance_index: number;
  promotion: { status: string; evidence: string[]; confidence: number };
}

function stableString(value: unknown): string {
  if (value === null || typeof value !== 'object') return JSON.stringify(value);
  if (Array.isArray(value)) return `[${value.map(stableString).join(',')}]`;
  return `{${Object.keys(value as Record<string, unknown>).sort().map((key) => `${JSON.stringify(key)}:${stableString((value as Record<string, unknown>)[key])}`).join(',')}}`;
}

function byteLength(value: unknown): number {
  return new TextEncoder().encode(stableString(value)).length;
}

async function contentDigest(value: Record<string, unknown>): Promise<string> {
  const clone = { ...value };
  delete clone.content_digest;
  const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(stableString(clone)));
  return `sha256:${Array.from(new Uint8Array(digest)).map((byte) => byte.toString(16).padStart(2, '0')).join('')}`;
}

function randomId(prefix: string): string {
  return `${prefix}-${crypto.randomUUID()}`;
}

function safeAuthorId(handle: string | null, fallback: string): string {
  return handle ? `author-${handle.toLowerCase()}` : `author-${fallback}`;
}

function challengeCode(): string | null {
  if (location.origin !== EXACT_ORIGIN) return 'WRONG_ORIGIN';
  if (window.top !== window) return 'IFRAME_BOUNDARY';
  if (document.querySelector('iframe[src*="captcha" i], iframe[src*="arkose" i], [data-testid*="captcha" i]')) return 'CAPTCHA_OR_TURNSTILE';
  if (document.querySelector('[data-testid="loginButton"], form[action*="login"]')) return 'SIGN_OUT_STATE';
  const headings = Array.from(document.querySelectorAll('main h1, main h2, [role="dialog"] h1, [role="dialog"] h2'))
    .map((element) => (element.textContent || '').replace(/\s+/g, ' ').trim())
    .join(' ');
  if (/verify (?:that it is you|your identity)|verification challenge/i.test(headings)) return 'VERIFICATION_CHALLENGE';
  if (/unusual activity|temporarily limited|account (?:is )?locked/i.test(headings)) return 'UNUSUAL_ACTIVITY';
  if (/rate limit exceeded|too many requests/i.test(headings)) return 'RATE_LIMIT';
  if (/before you continue|review (?:our )?(?:terms|privacy)/i.test(headings)) return 'CONSENT_SURFACE';
  return null;
}

export class LiveCollector {
  private state: LifecycleState = 'ARMED';
  private observations: Observation[] = [];
  private events: Array<{ event_code: string; at: string; safe_detail_code: string | null }> = [];
  private sessionId: string | null = null;
  private startedAt: number | null = null;
  private stoppedAt: number | null = null;
  private stopCode: string | null = null;
  private mutationObserver: MutationObserver | null = null;
  private intersectionObserver: IntersectionObserver | null = null;
  private durationTimer: number | null = null;
  private nodeKeys = new WeakMap<Element, string>();
  private ratios = new WeakMap<Element, number>();
  private seenSignatures = new Map<string, string>();
  private identityIndexes = new Map<string, number>();
  private nodeCounter = 0;
  private ambiguousCount = 0;
  private promotionCounts = { organic: 0, promoted: 0, ambiguous: 0 };
  private observationBytes = 0;
  private exportSnapshot: { id: string; sessionId: string; json: string; chunks: Array<[number, number]> } | null = null;
  private indicator: HTMLElement | null = null;

  constructor() {
    this.renderIndicator();
    document.addEventListener('visibilitychange', () => this.visibilityChanged());
  }

  status(): CollectorStatus {
    const now = this.stoppedAt ?? Date.now();
    return {
      state: this.state,
      observationCount: this.observations.length,
      organicCount: this.promotionCounts.organic,
      promotedCount: this.promotionCounts.promoted,
      ambiguousCount: this.ambiguousCount + this.promotionCounts.ambiguous,
      hardStopCode: this.stopCode,
      startedAt: this.startedAt === null ? null : new Date(this.startedAt).toISOString(),
      elapsedSeconds: this.startedAt === null ? 0 : Math.max(0, Math.floor((now - this.startedAt) / 1000)),
      autoScroll: false,
      networkRequests: 0,
      accountActions: 0,
    };
  }

  messageStatus(): CollectorResponse {
    return { ok: true, status: this.status() };
  }

  start(): CollectorResponse {
    if (!['ARMED', 'STOPPED'].includes(this.state)) return this.response(false, 'INVALID_STATE');
    const challenge = challengeCode();
    if (challenge) {
      this.hardStop(challenge);
      return this.response(false, challenge);
    }
    this.resetSession();
    this.state = 'CAPTURING';
    this.startedAt = Date.now();
    this.sessionId = randomId('live-dom');
    this.event('SESSION_STARTED');
    this.attach();
    this.durationTimer = window.setTimeout(() => this.limitStop('DURATION_LIMIT'), LIMITS.maxDurationSeconds * 1000);
    this.renderIndicator();
    return this.response(true);
  }

  stop(): CollectorResponse {
    if (!['CAPTURING', 'PAUSED_HIDDEN', 'ARMED'].includes(this.state)) return this.response(false, 'INVALID_STATE');
    this.detach();
    this.state = 'STOPPED';
    this.stoppedAt = Date.now();
    this.event('STOPPED_USER');
    this.renderIndicator();
    return this.response(true);
  }

  discard(): CollectorResponse {
    this.detach();
    this.resetSession();
    this.state = 'ARMED';
    this.renderIndicator();
    return this.response(true);
  }

  async exportPacket(): Promise<CollectorResponse> {
    if (!this.sessionId || !this.startedAt || this.observations.length === 0) return this.response(false, 'NOTHING_TO_EXPORT');
    const ended = this.stoppedAt ?? Date.now();
    const packet: Record<string, unknown> = {
      schema_version: '2.0.0',
      session: {
        session_id: this.sessionId,
        schema_version: '2.0.0',
        source: 'live_dom',
        started_at: new Date(this.startedAt).toISOString(),
        ended_at: new Date(ended).toISOString(),
        origin: EXACT_ORIGIN,
        collector_version: COLLECTOR_VERSION,
        privacy_profile: 'default_local',
        collection_mode: 'manual_scroll',
        limits: {
          max_candidates: LIMITS.maxCandidates,
          max_duration_seconds: LIMITS.maxDurationSeconds,
          max_packet_bytes: LIMITS.maxPacketBytes,
        },
      },
      observations: this.observations,
      collection_events: this.events,
      content_digest: '',
    };
    packet.content_digest = await contentDigest(packet);
    const json = stableString(packet);
    const totalBytes = new TextEncoder().encode(json).length;
    if (totalBytes + 1 > LIMITS.maxPacketBytes) {
      this.limitStop('PACKET_LIMIT');
      return this.response(false, 'PACKET_LIMIT');
    }
    const chunks: Array<[number, number]> = [];
    for (let start = 0; start < json.length;) {
      let end = Math.min(start + 262_144, json.length);
      // Do not split a UTF-16 surrogate pair across separately encoded Blob parts.
      if (end < json.length && /[\uD800-\uDBFF]/.test(json.charAt(end - 1))) end -= 1;
      chunks.push([start, end]);
      start = end;
    }
    const id = randomId('export');
    this.exportSnapshot = { id, sessionId: this.sessionId, json, chunks };
    return { ...this.response(true), export: { id, sessionId: this.sessionId, chunkCount: chunks.length, totalBytes } };
  }

  exportChunk(id: string, index: number): CollectorResponse {
    const snapshot = this.exportSnapshot;
    if (!snapshot || id !== snapshot.id || !Number.isInteger(index) || index < 0 || index >= snapshot.chunks.length) {
      return this.response(false, 'INVALID_EXPORT_CHUNK');
    }
    const [start, end] = snapshot.chunks[index]!;
    return { ...this.response(true), chunk: snapshot.json.slice(start, end) };
  }

  releaseExport(id: string): CollectorResponse {
    if (this.exportSnapshot?.id !== id) return this.response(false, 'INVALID_EXPORT_ID');
    this.exportSnapshot = null;
    return this.response(true);
  }

  private response(ok: boolean, error?: string): CollectorResponse {
    return { ok, status: this.status(), ...(error ? { error } : {}) };
  }

  private resetSession(): void {
    this.observations = [];
    this.events = [];
    this.sessionId = null;
    this.startedAt = null;
    this.stoppedAt = null;
    this.stopCode = null;
    this.ambiguousCount = 0;
    this.promotionCounts = { organic: 0, promoted: 0, ambiguous: 0 };
    this.observationBytes = 0;
    this.exportSnapshot = null;
    this.seenSignatures.clear();
    this.identityIndexes.clear();
    this.nodeKeys = new WeakMap();
    this.ratios = new WeakMap();
  }

  private event(code: string, detail: string | null = null): void {
    if (this.events.length < LIMITS.maxEvents) {
      this.events.push({ event_code: code, at: new Date().toISOString(), safe_detail_code: detail });
    }
  }

  private nodeKey(element: Element): string {
    let value = this.nodeKeys.get(element);
    if (!value) {
      value = `x-node-${++this.nodeCounter}`;
      this.nodeKeys.set(element, value);
    }
    return value;
  }

  private attach(): void {
    if (this.state !== 'CAPTURING' || this.intersectionObserver || this.mutationObserver) return;
    const challenge = challengeCode();
    if (challenge) return void this.hardStop(challenge);
    this.intersectionObserver = new IntersectionObserver((entries) => {
      for (const entry of entries) {
        const ratio = entry.isIntersecting ? entry.intersectionRatio : 0;
        this.ratios.set(entry.target, ratio);
        if (ratio >= LIMITS.minimumVisibilityRatio) this.process(entry.target);
      }
    }, { threshold: [0, LIMITS.minimumVisibilityRatio, 1] });
    this.mutationObserver = new MutationObserver((mutations) => {
      const challengeNow = challengeCode();
      if (challengeNow) return void this.hardStop(challengeNow);
      const changed = new Set<Element>();
      for (const mutation of mutations) {
        const target = mutation.target instanceof Element ? mutation.target : mutation.target.parentElement;
        const card = target?.closest(SELECTORS.post);
        if (card) changed.add(card);
        for (const node of mutation.addedNodes) {
          if (!(node instanceof Element)) continue;
          if (node.matches(SELECTORS.post)) this.observe(node);
          node.querySelectorAll(SELECTORS.post).forEach((element) => this.observe(element));
        }
      }
      changed.forEach((card) => this.process(card));
    });
    document.querySelectorAll(SELECTORS.post).forEach((element) => this.observe(element));
    this.mutationObserver.observe(document.querySelector('main') || document.body, { subtree: true, childList: true, characterData: true, attributes: true, attributeFilter: ['aria-label', 'data-testid', 'href'] });
  }

  private detach(): void {
    this.intersectionObserver?.disconnect();
    this.mutationObserver?.disconnect();
    this.intersectionObserver = null;
    this.mutationObserver = null;
    if (this.durationTimer !== null) window.clearTimeout(this.durationTimer);
    this.durationTimer = null;
    this.nodeKeys = new WeakMap();
    this.ratios = new WeakMap();
  }

  private observe(element: Element): void {
    if (element.parentElement?.closest(SELECTORS.post)) return;
    this.intersectionObserver?.observe(element);
  }

  private process(article: Element): void {
    if (this.state !== 'CAPTURING' || !this.sessionId || !this.startedAt) return;
    const ratio = Math.min(this.ratios.get(article) || 0, viewportVisibilityRatio(article));
    if (ratio < LIMITS.minimumVisibilityRatio || document.visibilityState !== 'visible') return;
    const parsed = parseCard(article);
    const identity = parsed.platformPostId || parsed.canonicalPermalink || `${parsed.handle || 'unknown'}:${parsed.displayedTimestamp || 'unknown'}:${parsed.visibleText || ''}`;
    const signature = stableString({ identity, text: parsed.visibleText, author: parsed.handle, promotion: parsed.promotion, media: parsed.media });
    const node = this.nodeKey(article);
    if (this.seenSignatures.get(node) === signature) return;
    const existingIndex = this.identityIndexes.get(identity);
    if (existingIndex !== undefined) {
      const existing = this.observations[existingIndex];
      this.seenSignatures.set(node, signature);
      if (existing && existing.promotion.status !== parsed.promotion && existing.promotion.status !== 'ambiguous') {
        const previousBytes = byteLength(existing);
        this.promotionCounts[existing.promotion.status as keyof typeof this.promotionCounts] -= 1;
        existing.promotion = {
          status: 'ambiguous',
          evidence: Array.from(new Set([...existing.promotion.evidence, parsed.promotionEvidence, 'manual_review'])),
          confidence: 0.5,
        };
        const uncertainties = existing.uncertainty as Array<Record<string, unknown>>;
        uncertainties.push({ code: 'PROMOTION_STATE_CHANGED', field: 'promotion', severity: 'review', requires_review: true, safe_detail: 'The visible promotion state changed during this session.' });
        this.promotionCounts.ambiguous += 1;
        this.observationBytes += byteLength(existing) - previousBytes;
        this.event('OBSERVATION_UPDATED', 'PROMOTION_STATE_CHANGED');
        this.renderIndicator();
      }
      if (parsed.uncertaintyCodes.includes('PROMPT_INJECTION')) this.hardStop('INJECTION_CONTENT');
      return;
    }
    if (this.observations.length >= LIMITS.maxCandidates) return void this.limitStop('QUEUE_LIMIT');

    const appearance = this.observations.length;
    const observationId = `${this.sessionId}-observation-${String(appearance).padStart(3, '0')}`;
    const provenanceId = `${this.sessionId}-provenance-${String(appearance).padStart(3, '0')}`;
    const uncertainties = parsed.uncertaintyCodes.map((code) => ({
      code,
      field: code === 'PROMPT_INJECTION' ? 'visible_text' : 'observation',
      severity: code === 'PROMPT_INJECTION' ? 'blocking' : 'review',
      requires_review: true,
      safe_detail: code === 'PROMPT_INJECTION' ? 'Visible post contains instruction-like text; it remains inert data.' : null,
    }));
    const ambiguous = parsed.uncertaintyCodes.some((code) => ['MISSING_PLATFORM_ID', 'MISSING_AUTHOR_HANDLE', 'MISSING_VISIBLE_CONTENT'].includes(code));
    if (ambiguous) this.ambiguousCount += 1;

    const observation: Observation = {
      observation_id: observationId,
      session_id: this.sessionId,
      appearance_index: appearance,
      top_level: true,
      visibility_ratio: Number(ratio.toFixed(6)),
      document_visible: true,
      platform_post_id: parsed.platformPostId,
      canonical_permalink: parsed.canonicalPermalink,
      visible_text: parsed.visibleText,
      displayed_timestamp: parsed.displayedTimestamp,
      authors: [{
        local_author_id: safeAuthorId(parsed.handle, String(appearance)),
        platform_author_id: null,
        display_name: parsed.displayName,
        handle: parsed.handle,
        role: parsed.uncertaintyCodes.includes('EMBEDDED_QUOTE_REVIEW_REQUIRED') ? 'quoting' : 'original',
        identity_confidence: parsed.handle ? 0.95 : 0.35,
        uncertainty_codes: parsed.handle ? [] : ['MISSING_AUTHOR_HANDLE'],
      }],
      relationships: [],
      media: parsed.media.map((media, index) => ({
        local_media_id: `${observationId}-media-${index}`,
        kind: media.kind,
        alt_text: media.altText,
        visible_description: null,
        perceptual_fingerprint: null,
        binary_collected: false,
        confidence: media.altText ? 0.9 : 0.6,
        provenance_ids: [provenanceId],
      })),
      promotion: {
        status: parsed.promotion,
        evidence: [parsed.promotionEvidence],
        confidence: parsed.promotion === 'organic' ? 0.8 : 1,
      },
      provenance: [{
        provenance_id: provenanceId,
        modality: 'live_dom',
        collector_version: COLLECTOR_VERSION,
        parser_or_ocr_version: PARSER_VERSION,
        field: 'visible_card',
        observed_at: new Date().toISOString(),
        video_time_ms: null,
        crop_xywh: null,
        confidence: ambiguous ? 0.5 : 0.9,
      }],
      uncertainty: uncertainties,
      input_location: {
        viewport_time_ms: Date.now() - this.startedAt,
        video_time_ms: null,
        crop_xywh: null,
      },
      preview_grade: parsed.preview.grade,
      preview_reasons: parsed.preview.reasons,
    };
    const nextBytes = this.observationBytes + byteLength(observation) + 1;
    // Reserve 1 MiB for session metadata, bounded events, digest and edits.
    if (nextBytes > LIMITS.maxPacketBytes - 1_048_576) return void this.limitStop('PACKET_LIMIT');
    this.seenSignatures.set(node, signature);
    this.observations.push(observation);
    this.observationBytes = nextBytes;
    this.promotionCounts[parsed.promotion] += 1;
    this.identityIndexes.set(identity, appearance);
    this.event('OBSERVATION_ACCEPTED', 'COUNT_ONLY');
    this.renderIndicator();

    if (parsed.uncertaintyCodes.includes('PROMPT_INJECTION')) return void this.hardStop('INJECTION_CONTENT');
    if (this.ambiguousCount / this.observations.length > LIMITS.maxAmbiguityRatio && this.observations.length >= 20) return void this.hardStop('AMBIGUITY_LIMIT');
    if (this.observations.length >= LIMITS.maxCandidates) this.limitStop('QUEUE_LIMIT');
  }

  private visibilityChanged(): void {
    if (document.visibilityState === 'hidden' && this.state === 'CAPTURING') {
      this.detach();
      this.state = 'PAUSED_HIDDEN';
      this.event('PAUSED_DOCUMENT_HIDDEN');
      this.renderIndicator();
    } else if (document.visibilityState === 'visible' && this.state === 'PAUSED_HIDDEN') {
      const challenge = challengeCode();
      if (challenge) return void this.hardStop(challenge);
      this.state = 'CAPTURING';
      this.attach();
      this.renderIndicator();
    }
  }

  private limitStop(code: string): void {
    this.detach();
    this.stopCode = code;
    this.stoppedAt = Date.now();
    this.state = 'LIMIT_REACHED';
    this.event(code);
    this.renderIndicator();
  }

  private hardStop(code: string): void {
    this.detach();
    const safe = HARD_STOPS.has(code) ? code : 'UNKNOWN_TOPOLOGY';
    this.stopCode = safe;
    this.stoppedAt = Date.now();
    this.state = 'ERROR';
    this.event(safe);
    this.renderIndicator();
  }

  private renderIndicator(): void {
    if (!this.indicator) {
      const host = document.createElement('div');
      host.id = 'xfi-lifecycle-indicator';
      host.style.cssText = 'position:fixed;right:16px;bottom:16px;z-index:2147483647;pointer-events:none';
      const shadow = host.attachShadow({ mode: 'closed' });
      const label = document.createElement('div');
      label.setAttribute('role', 'status');
      label.setAttribute('aria-live', 'polite');
      label.style.cssText = 'font:600 12px/1.2 -apple-system,BlinkMacSystemFont,sans-serif;padding:8px 10px;border-radius:999px;background:#111827;color:#fff;border:1px solid #4b5563;box-shadow:0 4px 16px rgba(0,0,0,.25)';
      shadow.append(label);
      document.documentElement.append(host);
      this.indicator = label;
    }
    const status = this.status();
    this.indicator.textContent = `XFI ${status.state.replace('_', ' ')} · ${status.observationCount}`;
    this.indicator.style.background = status.state === 'ERROR' ? '#991b1b' : status.state === 'CAPTURING' ? '#065f46' : '#111827';
  }
}

export default defineContentScript({
  matches: ['https://x.com/*'],
  runAt: 'document_idle',
  allFrames: false,
  noScriptStartedPostMessage: true,
  main() {
    const collector = new LiveCollector();
    browser.runtime.onMessage.addListener((message: unknown, sender, sendResponse) => {
      if (sender.id !== browser.runtime.id || !message || typeof message !== 'object' || !('type' in message)) return undefined;
      const command = message as CollectorCommand;
      switch (command.type) {
        case 'XFI_STATUS': sendResponse(collector.messageStatus()); return undefined;
        case 'XFI_START': sendResponse(collector.start()); return undefined;
        case 'XFI_STOP': sendResponse(collector.stop()); return undefined;
        case 'XFI_EXPORT':
          void collector.exportPacket().then(sendResponse, () => sendResponse({ ok: false, status: collector.status(), error: 'EXPORT_FAILED' }));
          return true;
        case 'XFI_EXPORT_CHUNK': sendResponse(collector.exportChunk(command.exportId, command.index)); return undefined;
        case 'XFI_EXPORT_RELEASE': sendResponse(collector.releaseExport(command.exportId)); return undefined;
        case 'XFI_DISCARD': sendResponse(collector.discard()); return undefined;
        default: return undefined;
      }
    });
  },
});
