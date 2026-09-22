import { browser } from 'wxt/browser';
import { COLLECTOR_VERSION, EXACT_ORIGIN, LIMITS, PARSER_VERSION, type CollectorCommand, type CollectorResponse, type CollectorSessionSnapshot, type CollectorStatus, type LifecycleState } from '../lib/contracts';
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
  private completedCount = 0;
  private partNumber = 1;
  private completedPromotionCounts = { organic: 0, promoted: 0, ambiguous: 0 };
  private completedAmbiguousCount = 0;
  private stopAfterRollover = false;
  private rollingOver = false;
  private resumeScrollAfterRollover = false;
  private recentPartIdentities = new Set<string>();
  private exportSnapshot: { id: string; sessionId: string; json: string; chunks: Array<[number, number]> } | null = null;
  private autoScroll = false;
  private assistedEver = false;
  private scrollTimer: number | null = null;
  private scrollPauseReason: string | null = null;
  private lastDomChange = Date.now();
  private lastScrollProgress = Date.now();
  private lastScrollY = 0;
  private lastScrollObservationCount = 0;
  private scrollDelay = 850;
  private scrollStalls = 0;
  private readonly stopScrollOnInput = (event: Event): void => {
    if (!event.isTrusted || !this.autoScroll) return;
    this.stopScrollInternal('USER_INPUT');
    void this.persist();
  };
  private revision = 0;
  private committedSnapshot: CollectorSessionSnapshot | null = null;
  private queuedSnapshot: CollectorSessionSnapshot | null = null;
  private sendingSnapshot = false;
  private writeWaiters: Array<{ revision: number; sessionId: string | null; resolve: (saved: boolean) => void }> = [];
  private blockedConfirmed = false;
  private clearedRevision = 0;
  private readonly clientId = crypto.randomUUID();
  private readonly documentStartedAt = performance.timeOrigin;
  private readonly restored: Promise<void>;

  constructor() {
    document.addEventListener('visibilitychange', () => this.visibilityChanged());
    this.restored = this.restore();
  }

  ready(): Promise<void> { return this.restored; }

  private async restore(): Promise<void> {
    try {
      const reply = await browser.runtime.sendMessage({ type: 'XFI_SESSION_READ', clientId: this.clientId, documentStartedAt: this.documentStartedAt }) as { snapshot?: CollectorSessionSnapshot | null; blocked?: boolean };
      const snapshot = reply?.snapshot;
      if (snapshot && (!Array.isArray(snapshot.observations) || !Array.isArray(snapshot.events) || !snapshot.sessionId)) throw new Error('INVALID_SESSION_SNAPSHOT');
      if (!snapshot) {
        if (reply?.blocked) { this.blockedConfirmed = true; this.state = 'ERROR'; this.stopCode = 'RETENTION_FAILURE'; this.stoppedAt = Date.now(); }
        return;
      }
      this.committedSnapshot = structuredClone(snapshot);
      this.state = snapshot.state;
      this.revision = snapshot.revision;
      this.observations = snapshot.observations as Observation[];
      this.events = snapshot.events;
      this.sessionId = snapshot.sessionId;
      this.startedAt = snapshot.startedAt;
      this.stoppedAt = snapshot.stoppedAt;
      this.stopCode = snapshot.stopCode;
      this.ambiguousCount = snapshot.ambiguousCount;
      this.promotionCounts = snapshot.promotionCounts;
      this.observationBytes = snapshot.observationBytes;
      this.completedCount = snapshot.completedCount || 0;
      this.partNumber = snapshot.partNumber || 1;
      this.completedPromotionCounts = snapshot.completedPromotionCounts || { organic: 0, promoted: 0, ambiguous: 0 };
      this.completedAmbiguousCount = snapshot.completedAmbiguousCount || 0;
      this.stopAfterRollover = snapshot.stopAfterRollover || false;
      this.assistedEver = snapshot.assistedEver;
      this.scrollPauseReason = snapshot.scrollPauseReason;
      if (this.state === 'ROLLING_OVER') {
        this.state = 'ERROR';
        this.stopCode = 'AUTO_EXPORT_INTERRUPTED';
        this.stoppedAt = Date.now();
        this.event('AUTO_EXPORT_INTERRUPTED');
        void this.persist();
      }
      if (reply?.blocked) {
        this.blockedConfirmed = true;
        this.state = 'ERROR';
        this.stopCode = 'RETENTION_FAILURE';
        this.stoppedAt = Date.now();
        return;
      }
      this.identityIndexes.clear();
      this.observations.forEach((observation, index) => {
        const stable = [observation.platform_post_id, observation.canonical_permalink].filter((value): value is string => !!value);
        const keys = stable.length > 0 ? stable : [`${(observation.authors as Array<{ handle?: string | null }>)[0]?.handle || 'unknown'}:${observation.displayed_timestamp || 'unknown'}:${observation.visible_text || ''}`];
        keys.forEach((identity) => this.identityIndexes.set(String(identity), index));
      });
      // Auto-scroll never resumes itself after a navigation. The user must opt in again.
      this.autoScroll = false;
      // Refreshing an active page hides the old document before it unloads. If
      // that pause was committed, the new visible document must reconnect it;
      // an initially hidden document remains paused until it becomes visible.
      const resumeAfterRefresh = this.state === 'CAPTURING' ||
        (this.state === 'PAUSED_HIDDEN' && document.visibilityState === 'visible');
      if (resumeAfterRefresh) {
        this.state = 'CAPTURING';
        this.scrollPauseReason = 'PAGE_RELOADED';
        this.event('RECONNECTED_AFTER_PAGE_RELOAD');
        this.attach();
        const remaining = Math.max(0, LIMITS.maxDurationSeconds * 1000 - (Date.now() - (this.startedAt || Date.now())));
        this.durationTimer = window.setTimeout(() => this.limitStop('DURATION_LIMIT'), remaining);
        this.persist();
      }
    } catch { this.blockedConfirmed = true; this.state = 'ERROR'; this.stopCode = 'RETENTION_FAILURE'; this.stoppedAt = Date.now(); }
  }

  private snapshot(): CollectorSessionSnapshot {
    return { revision: ++this.revision, state: this.state, observations: this.observations, events: this.events, sessionId: this.sessionId,
      startedAt: this.startedAt, stoppedAt: this.stoppedAt, stopCode: this.stopCode, ambiguousCount: this.ambiguousCount,
      promotionCounts: this.promotionCounts, observationBytes: this.observationBytes, assistedEver: this.assistedEver,
      scrollPauseReason: this.scrollPauseReason, completedCount: this.completedCount, partNumber: this.partNumber,
      completedPromotionCounts: this.completedPromotionCounts, completedAmbiguousCount: this.completedAmbiguousCount,
      stopAfterRollover: this.stopAfterRollover };
  }

  private persist(): Promise<boolean> {
    const snapshot = this.snapshot();
    this.queuedSnapshot = snapshot; // Coalesce rapid cards while one write is in flight.
    const result = new Promise<boolean>((resolve) => this.writeWaiters.push({ revision: snapshot.revision, sessionId: snapshot.sessionId, resolve }));
    void this.flushSnapshot();
    return result;
  }

  private async flushSnapshot(): Promise<void> {
    if (this.sendingSnapshot || !this.queuedSnapshot) return;
    const snapshot = structuredClone(this.queuedSnapshot);
    this.queuedSnapshot = null;
    this.sendingSnapshot = true;
    let saved = false;
    let error = 'SESSION_STORAGE_WRITE_FAILED';
    try {
      const reply = await browser.runtime.sendMessage({ type: 'XFI_SESSION_WRITE', clientId: this.clientId, snapshot }) as { ok?: boolean; error?: string };
      saved = reply?.ok === true;
      error = reply?.error || error;
    } catch { /* The current page is stopped below if this is its session. */ }
    if (saved && snapshot.revision > this.clearedRevision &&
      (!this.committedSnapshot || snapshot.revision > this.committedSnapshot.revision)) {
      this.committedSnapshot = snapshot;
    }
    const resolved = this.writeWaiters.filter((waiter) => waiter.revision <= snapshot.revision);
    this.writeWaiters = this.writeWaiters.filter((waiter) => waiter.revision > snapshot.revision);
    for (const waiter of resolved) waiter.resolve(saved && waiter.sessionId === snapshot.sessionId);
    if (!saved && snapshot.sessionId === this.sessionId &&
      (error !== 'STALE_SESSION_WRITE' || snapshot.revision >= this.revision)) {
      this.persistenceFailure(error, snapshot.sessionId);
    }
    this.sendingSnapshot = false;
    void this.flushSnapshot();
  }

  private async clearPersisted(discardedSessionId: string | null): Promise<boolean> {
    if (!discardedSessionId) return true;
    const revision = ++this.revision;
    try {
      const reply = await browser.runtime.sendMessage({ type: 'XFI_SESSION_CLEAR', clientId: this.clientId, revision, sessionId: discardedSessionId }) as { ok?: boolean; stale?: boolean };
      if (reply?.ok && !reply.stale) { this.clearedRevision = revision; return true; }
    } catch { /* Mark the prior session blocked below. */ }
    this.blockDiscardedSession(discardedSessionId);
    return false;
  }

  private blockDiscardedSession(sessionId: string | null): void {
    if (!sessionId) return;
    try { void browser.runtime.sendMessage({ type: 'XFI_SESSION_FAIL_CLOSED', clientId: this.clientId, revision: ++this.revision, sessionId })
      .then((reply: { ok?: boolean }) => { if (reply?.ok && (!this.sessionId || this.sessionId === sessionId)) this.blockedConfirmed = true; }, () => undefined); }
    catch { /* The background is unavailable; see storage durability limitation. */ }
  }

  private persistenceFailure(reason: string, sessionId: string | null): void {
    if (!sessionId || this.sessionId !== sessionId || this.stopCode === 'RETENTION_FAILURE') return;
    this.queuedSnapshot = null;
    for (const waiter of this.writeWaiters) waiter.resolve(false);
    this.writeWaiters = [];
    this.detach();
    this.stopCode = 'RETENTION_FAILURE';
    this.stoppedAt = Date.now();
    this.state = 'ERROR';
    this.event('RETENTION_FAILURE', reason);
    try { void browser.runtime.sendMessage({ type: 'XFI_SESSION_FAIL_CLOSED', clientId: this.clientId, revision: ++this.revision, sessionId })
      .then((reply: { ok?: boolean }) => { if (reply?.ok && this.sessionId === sessionId) this.blockedConfirmed = true; }, () => undefined); }
    catch { /* The active page still remains stopped. */ }
  }

  status(): CollectorStatus {
    const committed = this.committedSnapshot;
    const committedState = this.blockedConfirmed ? 'ERROR' : committed?.state || 'ARMED';
    const committedStopCode = this.blockedConfirmed ? 'RETENTION_FAILURE' : committed?.stopCode || null;
    const committedSessionId = committed?.sessionId || null;
    const pendingObservationCount = this.sessionId && this.sessionId === committedSessionId
      ? Math.max(0, this.observations.length - (committed?.observations.length || 0))
      : this.observations.length;
    const startedAt = committed?.startedAt || null;
    const now = committed?.stoppedAt ?? Date.now();
    return {
      state: committedState,
      pendingState: this.state !== committedState ? this.state : null,
      pendingObservationCount,
      pendingChanges: !this.blockedConfirmed && this.revision > (committed?.revision || this.clearedRevision),
      pendingPersistenceFailure: this.state === 'ERROR' && this.stopCode === 'RETENTION_FAILURE' && !this.blockedConfirmed,
      observationCount: committed?.observations.length || 0,
      totalObservationCount: (committed?.completedCount || 0) + (committed?.observations.length || 0),
      partNumber: committed?.partNumber || 1,
      organicCount: (committed?.completedPromotionCounts?.organic || 0) + (committed?.promotionCounts.organic || 0),
      promotedCount: (committed?.completedPromotionCounts?.promoted || 0) + (committed?.promotionCounts.promoted || 0),
      ambiguousCount: (committed?.completedAmbiguousCount || 0) + (committed?.ambiguousCount || 0) + (committed?.promotionCounts.ambiguous || 0),
      hardStopCode: committedStopCode,
      startedAt: startedAt === null ? null : new Date(startedAt).toISOString(),
      elapsedSeconds: startedAt === null ? 0 : Math.max(0, Math.floor((now - startedAt) / 1000)),
      autoScroll: this.autoScroll,
      scrollPauseReason: committed?.scrollPauseReason || this.scrollPauseReason,
      networkRequests: 0,
      accountActions: 0,
    };
  }

  messageStatus(): CollectorResponse {
    return { ok: true, status: this.status() };
  }

  async start(): Promise<CollectorResponse> {
    if (!['ARMED', 'STOPPED'].includes(this.state)) return this.response(false, 'INVALID_STATE');
    const challenge = challengeCode();
    if (challenge) {
      this.hardStop(challenge);
      return this.response(false, challenge);
    }
    this.resetSession();
    this.completedCount = 0;
    this.partNumber = 1;
    this.completedPromotionCounts = { organic: 0, promoted: 0, ambiguous: 0 };
    this.completedAmbiguousCount = 0;
    this.stopAfterRollover = false;
    this.recentPartIdentities.clear();
    this.state = 'CAPTURING';
    this.startedAt = Date.now();
    this.sessionId = randomId('live-dom');
    this.event('SESSION_STARTED');
    this.attach();
    this.durationTimer = window.setTimeout(() => this.limitStop('DURATION_LIMIT'), LIMITS.maxDurationSeconds * 1000);
    const saved = await this.persist();
    return this.response(saved && this.state === 'CAPTURING', !saved ? 'SESSION_STORAGE_WRITE_FAILED' : this.state === 'CAPTURING' ? undefined : 'STATE_CHANGED');
  }

  async stop(): Promise<CollectorResponse> {
    if (this.state === 'ROLLING_OVER') {
      this.stopAfterRollover = true;
      const saved = await this.persist();
      return this.response(saved, saved ? undefined : 'SESSION_STORAGE_WRITE_FAILED');
    }
    if (!['CAPTURING', 'PAUSED_HIDDEN', 'ARMED'].includes(this.state)) return this.response(false, 'INVALID_STATE');
    this.detach();
    this.state = 'STOPPED';
    this.stoppedAt = Date.now();
    this.event('STOPPED_USER');
    if (!this.sessionId) return this.response(true);
    const saved = await this.persist();
    return this.response(saved && this.state === 'STOPPED', !saved ? 'SESSION_STORAGE_WRITE_FAILED' : this.state === 'STOPPED' ? undefined : 'STATE_CHANGED');
  }

  startScroll(): CollectorResponse {
    if (this.state !== 'CAPTURING' || document.visibilityState !== 'visible') return this.response(false, 'SCROLL_REQUIRES_VISIBLE_CAPTURE');
    const challenge = challengeCode();
    if (challenge) { this.hardStop(challenge); return this.response(false, challenge); }
    if (this.autoScroll) return this.response(true);
    this.autoScroll = true;
    this.assistedEver = true;
    this.scrollPauseReason = null;
    this.lastDomChange = Date.now();
    this.lastScrollProgress = Date.now();
    this.lastScrollY = window.scrollY;
    this.lastScrollObservationCount = this.observations.length;
    this.scrollDelay = 850;
    this.scrollStalls = 0;
    for (const type of ['pointermove', 'mousedown', 'wheel', 'touchstart', 'keydown']) {
      document.addEventListener(type, this.stopScrollOnInput, { capture: true, passive: true });
    }
    this.event('ASSISTED_SCROLL_STARTED');
    this.persist();
    this.scheduleScroll();
    return this.response(true);
  }

  stopScroll(): CollectorResponse {
    this.stopScrollInternal('USER_STOP');
    this.persist();
    return this.response(true);
  }

  private stopScrollInternal(reason: string): void {
    if (this.scrollTimer !== null) window.clearTimeout(this.scrollTimer);
    this.scrollTimer = null;
    for (const type of ['pointermove', 'mousedown', 'wheel', 'touchstart', 'keydown']) {
      document.removeEventListener(type, this.stopScrollOnInput, true);
    }
    if (this.autoScroll) this.event('ASSISTED_SCROLL_STOPPED', reason);
    this.autoScroll = false;
    this.scrollPauseReason = reason;
  }

  private scheduleScroll(): void {
    if (!this.autoScroll) return;
    this.scrollTimer = window.setTimeout(() => this.scrollTick(), this.scrollDelay);
  }

  private scrollTarget(): HTMLElement | null {
    const eligible = (element: HTMLElement): boolean => {
      const style = getComputedStyle(element);
      return /(auto|scroll)/.test(style.overflowY) && element.scrollHeight > element.clientHeight + 8;
    };
    for (const post of Array.from(document.querySelectorAll(SELECTORS.post))) {
      if (post.parentElement?.closest(SELECTORS.post) || viewportVisibilityRatio(post) < LIMITS.minimumVisibilityRatio) continue;
      for (let ancestor = post.parentElement; ancestor; ancestor = ancestor.parentElement) {
        if (ancestor instanceof HTMLElement && eligible(ancestor)) return ancestor;
      }
    }
    const root = document.scrollingElement;
    return root instanceof HTMLElement && root.scrollHeight > window.innerHeight + 8 ? root : null;
  }

  private scrollTick(): void {
    this.scrollTimer = null;
    if (!this.autoScroll) return;
    const challenge = challengeCode();
    if (challenge) return void this.hardStop(challenge);
    if (this.state !== 'CAPTURING' || document.visibilityState !== 'visible') return void this.stopScrollInternal('HIDDEN_OR_STOPPED');
    const now = Date.now();
    if (now - this.lastScrollProgress > 30_000) {
      this.stopScrollInternal('AUTO_SCROLL_NO_PROGRESS');
      void this.persist();
      return;
    }
    // Wait for visible cards to hydrate and process before moving the viewport.
    if (now - this.lastDomChange < 450 || this.status().pendingObservationCount > 0) {
      this.scrollDelay = Math.min(2200, Math.round(this.scrollDelay * 1.15));
      return void this.scheduleScroll();
    }
    document.querySelectorAll(SELECTORS.post).forEach((card) => {
      if (!card.parentElement?.closest(SELECTORS.post) && viewportVisibilityRatio(card) >= LIMITS.minimumVisibilityRatio) {
        this.ratios.set(card, 1);
        this.process(card);
      }
    });
    if (this.state !== 'CAPTURING') return;
    const gained = this.observations.length - this.lastScrollObservationCount;
    if (gained > 0) {
      this.lastScrollProgress = now;
      this.lastScrollObservationCount = this.observations.length;
      this.scrollDelay = Math.max(650, Math.round(this.scrollDelay * 0.88));
    } else {
      this.scrollDelay = Math.min(2200, Math.round(this.scrollDelay * 1.12));
    }
    const step = Math.min(160, Math.max(80, Math.floor(innerHeight * 0.16)));
    const target = this.scrollTarget();
    if (target) {
      const oldTop = target.scrollTop;
      target.scrollTop = oldTop + step;
      if (target.scrollTop <= oldTop) {
        this.scrollStalls += 1;
        this.scrollPauseReason = oldTop + target.clientHeight >= target.scrollHeight - 2 ? 'END_OF_FEED' : 'NO_SCROLL_MOVEMENT';
        if (this.scrollStalls >= 3) { this.stopScrollInternal(this.scrollPauseReason); void this.persist(); return; }
        this.scrollDelay = Math.min(2200, Math.round(this.scrollDelay * 1.3));
      } else {
        this.scrollStalls = 0;
        this.scrollPauseReason = target === document.scrollingElement ? 'DOCUMENT_SCROLL' : 'NESTED_FEED_SCROLL';
      }
      this.lastScrollY = target.scrollTop;
      this.scheduleScroll();
      return;
    }
    this.stopScrollInternal('NO_SCROLLABLE_FEED');
    void this.persist();
  }

  async discard(): Promise<CollectorResponse> {
    this.detach();
    const discardedSessionId = this.sessionId;
    this.state = 'PAUSED_HIDDEN';
    const cleared = await this.clearPersisted(discardedSessionId);
    if (!cleared) {
      this.state = 'ERROR';
      this.stopCode = 'RETENTION_FAILURE';
      return this.response(false, 'SESSION_STORAGE_WRITE_FAILED');
    }
    this.resetSession();
    this.completedCount = 0;
    this.partNumber = 1;
    this.completedPromotionCounts = { organic: 0, promoted: 0, ambiguous: 0 };
    this.completedAmbiguousCount = 0;
    this.stopAfterRollover = false;
    this.recentPartIdentities.clear();
    this.committedSnapshot = null;
    this.exportSnapshot = null;
    this.blockedConfirmed = false;
    this.state = 'ARMED';
    return this.response(true);
  }

  async exportPacket(): Promise<CollectorResponse> {
    const committed = this.committedSnapshot;
    if (!committed?.sessionId || !committed.startedAt || committed.observations.length === 0) return this.response(false, 'NOTHING_TO_EXPORT');
    const ended = committed.stoppedAt ?? Date.now();
    const packet: Record<string, unknown> = {
      schema_version: '2.0.0',
      session: {
        session_id: committed.sessionId,
        schema_version: '2.0.0',
        source: 'live_dom',
        started_at: new Date(committed.startedAt).toISOString(),
        ended_at: new Date(ended).toISOString(),
        origin: EXACT_ORIGIN,
        collector_version: COLLECTOR_VERSION,
        privacy_profile: 'default_local',
        collection_mode: committed.assistedEver ? 'assisted_scroll' : 'manual_scroll',
        limits: {
          max_candidates: LIMITS.maxCandidates,
          max_duration_seconds: LIMITS.maxDurationSeconds,
          max_packet_bytes: LIMITS.maxPacketBytes,
        },
      },
      observations: committed.observations,
      collection_events: committed.events,
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
    this.exportSnapshot = { id, sessionId: committed.sessionId, json, chunks };
    return { ...this.response(true), export: { id, sessionId: committed.sessionId, chunkCount: chunks.length, totalBytes } };
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

  async completeRollover(sessionId: string): Promise<CollectorResponse> {
    if (this.state !== 'ROLLING_OVER' || this.sessionId !== sessionId) return this.response(false, 'STALE_ROLLOVER');
    const completed = this.observations.length;
    const partPromotionCounts = { ...this.promotionCounts };
    const partAmbiguousCount = this.ambiguousCount;
    const priorSessionId = this.sessionId;
    const shouldScroll = this.resumeScrollAfterRollover;
    const shouldStop = this.stopAfterRollover;
    this.recentPartIdentities = new Set(this.observations.slice(-12).flatMap((item) =>
      [item.platform_post_id, item.canonical_permalink].filter((value): value is string => typeof value === 'string' && !!value)));
    this.detach();
    this.resetSession();
    this.completedCount += completed;
    this.completedPromotionCounts.organic += partPromotionCounts.organic;
    this.completedPromotionCounts.promoted += partPromotionCounts.promoted;
    this.completedPromotionCounts.ambiguous += partPromotionCounts.ambiguous;
    this.completedAmbiguousCount += partAmbiguousCount;
    this.partNumber += 1;
    this.state = shouldStop ? 'STOPPED' : 'CAPTURING';
    this.sessionId = randomId('live-dom');
    this.startedAt = Date.now();
    this.event(shouldStop ? 'STOPPED_USER' : 'SESSION_CONTINUED', priorSessionId);
    if (!shouldStop) {
      this.attach();
      this.durationTimer = window.setTimeout(() => this.limitStop('DURATION_LIMIT'), LIMITS.maxDurationSeconds * 1000);
    } else this.stoppedAt = Date.now();
    const saved = await this.persist();
    this.rollingOver = false;
    this.resumeScrollAfterRollover = false;
    this.stopAfterRollover = false;
    if (saved && shouldScroll && !shouldStop) this.startScroll();
    return this.response(saved, saved ? undefined : 'SESSION_STORAGE_WRITE_FAILED');
  }

  private async rollover(reason: string): Promise<void> {
    if (this.rollingOver || this.state !== 'CAPTURING' || !this.sessionId) return;
    this.rollingOver = true;
    this.resumeScrollAfterRollover = this.autoScroll;
    this.state = 'ROLLING_OVER';
    this.event('PART_ROLLOVER', reason);
    this.detach();
    const saved = await this.persist();
    if (!saved) { this.rollingOver = false; return; }
    try {
      const reply = await browser.runtime.sendMessage({ type: 'XFI_AUTO_SAVE_EXPORT', clientId: this.clientId, sessionId: this.sessionId }) as { ok?: boolean; error?: string };
      if (reply?.ok) return; // The background acknowledges only after a verified file completion.
      this.stopCode = reply?.error || 'AUTO_EXPORT_FAILED';
    } catch { this.stopCode = 'AUTO_EXPORT_FAILED'; }
    this.rollingOver = false;
    this.resumeScrollAfterRollover = false;
    this.stopAfterRollover = false;
    this.detach();
    this.state = 'ERROR';
    this.stoppedAt = Date.now();
    this.event('AUTO_EXPORT_FAILED', this.stopCode);
    void this.persist();
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
    this.rollingOver = false;
    this.assistedEver = false;
    this.autoScroll = false;
    this.scrollPauseReason = null;
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

  private identityKeys(parsed: ReturnType<typeof parseCard>): string[] {
    return Array.from(new Set([
      parsed.platformPostId,
      parsed.canonicalPermalink,
      `${parsed.handle || 'unknown'}:${parsed.displayedTimestamp || 'unknown'}:${parsed.visibleText || ''}`,
    ].filter((value): value is string => !!value)));
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
      this.lastDomChange = Date.now();
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
    this.stopScrollInternal('CAPTURE_STOPPED');
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
    const identities = this.identityKeys(parsed);
    if (identities.some((candidate) => this.recentPartIdentities.has(candidate))) return;
    const identity = identities[0]!;
    const signature = stableString({ identity, text: parsed.visibleText, author: parsed.handle, promotion: parsed.promotion, media: parsed.media, quote: parsed.quote, links: parsed.outboundLinks });
    const node = this.nodeKey(article);
    if (this.seenSignatures.get(node) === signature) return;
    const existingIndex = identities.map((candidate) => this.identityIndexes.get(candidate)).find((candidate) => candidate !== undefined);
    if (existingIndex !== undefined) {
      const existing = this.observations[existingIndex];
      const beforeUpdate = existing ? structuredClone(existing) : null;
      const beforeBytes = this.observationBytes;
      const beforeCounts = { ...this.promotionCounts };
      const beforeEvents = this.events.length;
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
      }
      if (existing) {
        const before = byteLength(existing);
        let enriched = false;
        if ((!existing.visible_text || String(parsed.visibleText || '').length > String(existing.visible_text).length) && parsed.visibleText) { existing.visible_text = parsed.visibleText; enriched = true; }
        const priorQuote = existing.quote_context as { platform_post_id?: string | null; handle?: string | null; visible_text?: string | null; media?: unknown[] } | null;
        if (parsed.quote && (!priorQuote || (
          (!priorQuote.platform_post_id || !!parsed.quote.id) &&
          (!priorQuote.handle || !!parsed.quote.handle) &&
          String(parsed.quote.text || '').length >= String(priorQuote.visible_text || '').length &&
          parsed.quote.media.length >= (priorQuote.media?.length || 0) &&
          (String(parsed.quote.text || '').length > String(priorQuote.visible_text || '').length || parsed.quote.media.length > (priorQuote.media?.length || 0) || (!priorQuote.platform_post_id && !!parsed.quote.id))
        ))) {
          existing.quote_context = { platform_post_id: parsed.quote.id, canonical_permalink: parsed.quote.permalink, display_name: parsed.quote.displayName,
            handle: parsed.quote.handle, visible_text: parsed.quote.text, media: parsed.quote.media.map((item) => ({ kind: item.kind, alt_text: item.altText })) };
          existing.relationships = parsed.quote.id ? [{ kind: 'quotes', source_local_post_id: `${existing.observation_id}-quoted-source`,
            source_platform_post_id: parsed.quote.id, confidence: 0.9, provenance_ids: [(existing.provenance as Array<{ provenance_id: string }>)[0]!.provenance_id] }] : [];
          enriched = true;
        }
        if (parsed.outboundLinks.length > (existing.outbound_links as unknown[]).length) { existing.outbound_links = parsed.outboundLinks; enriched = true; }
        const media = existing.media as Array<Record<string, unknown>>;
        if (parsed.media.length > media.length) {
          const provenanceId = (existing.provenance as Array<{ provenance_id: string }>)[0]!.provenance_id;
          existing.media = parsed.media.map((item, index) => ({ local_media_id: `${existing.observation_id}-media-${index}`, kind: item.kind, alt_text: item.altText,
            visible_description: item.visibleDescription || null, perceptual_fingerprint: null, binary_collected: false, confidence: item.altText ? 0.9 : 0.6, provenance_ids: [provenanceId] }));
          enriched = true;
        }
        const uncertainties = existing.uncertainty as Array<{ code: string }>;
        for (const code of parsed.uncertaintyCodes) if (!uncertainties.some((item) => item.code === code) && uncertainties.length < 64) {
          uncertainties.push({ code, field: 'observation', severity: 'review', requires_review: true, safe_detail: null } as { code: string }); enriched = true;
        }
        existing.last_observed_at = new Date().toISOString();
        this.observationBytes += byteLength(existing) - before;
        if (enriched) this.event('OBSERVATION_UPDATED', 'CONTEXT_ENRICHED');
      }
      if (this.observationBytes + 65_536 > LIMITS.maxRefreshRecoveryBytes) {
        if (beforeUpdate) this.observations[existingIndex] = beforeUpdate;
        this.observationBytes = beforeBytes;
        this.promotionCounts = beforeCounts;
        this.events.length = beforeEvents;
        return void this.rollover('REFRESH_RECOVERY_LIMIT');
      }
      if (parsed.uncertaintyCodes.includes('PROMPT_INJECTION')) this.hardStop('INJECTION_CONTENT');
      identities.forEach((candidate) => this.identityIndexes.set(candidate, existingIndex));
      this.persist();
      return;
    }
    if (this.observations.length >= LIMITS.maxCandidates) return void this.rollover('QUEUE_LIMIT');

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
      first_observed_at: new Date().toISOString(),
      last_observed_at: new Date().toISOString(),
      outbound_links: parsed.outboundLinks,
      quote_context: parsed.quote ? { platform_post_id: parsed.quote.id, canonical_permalink: parsed.quote.permalink, display_name: parsed.quote.displayName,
        handle: parsed.quote.handle, visible_text: parsed.quote.text, media: parsed.quote.media.map((item) => ({ kind: item.kind, alt_text: item.altText })) } : null,
      displayed_timestamp: parsed.displayedTimestamp,
      authors: [{
        local_author_id: safeAuthorId(parsed.handle, String(appearance)),
        platform_author_id: null,
        display_name: parsed.displayName,
        handle: parsed.handle,
        role: parsed.quote ? 'quoting' : 'original',
        identity_confidence: parsed.handle ? 0.95 : 0.35,
        uncertainty_codes: parsed.handle ? [] : ['MISSING_AUTHOR_HANDLE'],
      }],
      relationships: parsed.quote?.id ? [{ kind: 'quotes', source_local_post_id: `${observationId}-quoted-source`, source_platform_post_id: parsed.quote.id, confidence: 0.9, provenance_ids: [provenanceId] }] : [],
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
    if (nextBytes > LIMITS.maxPacketBytes - 1_048_576) return void (this.observations.length ? this.rollover('PACKET_LIMIT') : this.limitStop('PACKET_LIMIT'));
    // A refresh-safe snapshot is intentionally smaller than the export ceiling.
    // Reserve metadata headroom so the candidate is never accepted only to fail
    // its mandatory background persistence write afterwards.
    if (this.observationBytes + byteLength(observation) + 65_536 > LIMITS.maxRefreshRecoveryBytes) {
      return void (this.observations.length ? this.rollover('REFRESH_RECOVERY_LIMIT') : this.limitStop('REFRESH_RECOVERY_LIMIT'));
    }
    this.seenSignatures.set(node, signature);
    this.observations.push(observation);
    this.observationBytes = nextBytes;
    this.promotionCounts[parsed.promotion] += 1;
    // A text-only fallback is an alias only when no stable X identity has arrived;
    // otherwise repeated boilerplate in separate posts must not collapse records.
    (identities.length > 1 ? identities.slice(0, -1) : identities).forEach((candidate) => this.identityIndexes.set(candidate, appearance));
    this.event('OBSERVATION_ACCEPTED', 'COUNT_ONLY');
    this.persist();

    if (parsed.uncertaintyCodes.includes('PROMPT_INJECTION')) return void this.hardStop('INJECTION_CONTENT');
    if (this.ambiguousCount / this.observations.length > LIMITS.maxAmbiguityRatio && this.observations.length >= 20) return void this.hardStop('AMBIGUITY_LIMIT');
    if (this.observations.length >= LIMITS.maxCandidates) void this.rollover('QUEUE_LIMIT');
  }

  private visibilityChanged(): void {
    if (document.visibilityState === 'hidden' && this.state === 'CAPTURING') {
      this.detach();
      this.state = 'PAUSED_HIDDEN';
      this.event('PAUSED_DOCUMENT_HIDDEN');
      this.persist();
    } else if (document.visibilityState === 'visible' && this.state === 'PAUSED_HIDDEN') {
      const challenge = challengeCode();
      if (challenge) return void this.hardStop(challenge);
      this.state = 'CAPTURING';
      this.attach();
      this.persist();
    }
  }

  private limitStop(code: string): void {
    this.detach();
    this.stopCode = code;
    this.stoppedAt = Date.now();
    this.state = 'LIMIT_REACHED';
    this.event(code);
    this.persist();
  }

  private hardStop(code: string): void {
    this.detach();
    const safe = HARD_STOPS.has(code) ? code : 'UNKNOWN_TOPOLOGY';
    this.stopCode = safe;
    this.stoppedAt = Date.now();
    this.state = 'ERROR';
    this.event(safe);
    this.persist();
  }

}

class CounterBubble {
  private readonly host = document.createElement('div');
  private readonly count: HTMLElement;
  private readonly timer: number;

  constructor(private readonly collector: LiveCollector) {
    this.host.id = 'xfi-counter-bubble';
    this.host.setAttribute('data-xfi-counter', '');
    const shadow = this.host.attachShadow({ mode: 'closed' });
    const style = document.createElement('style');
    style.textContent = ':host { all: initial; position: fixed; z-index: 2147483647; top: 78px; right: 16px; pointer-events: none; } .bubble { display: inline-flex; align-items: baseline; gap: 5px; min-width: 60px; padding: 7px 10px; border: 1px solid #42718a; border-radius: 999px; background: #0b1220e8; box-shadow: 0 3px 12px #0007; color: #f1f8ff; font: 700 13px/1.1 system-ui, sans-serif; } small { color: #9bbed0; font: 600 10px/1 system-ui, sans-serif; }';
    const bubble = document.createElement('div');
    bubble.className = 'bubble';
    this.count = document.createElement('span');
    const label = document.createElement('small'); label.textContent = 'cards';
    bubble.append(this.count, label);
    shadow.append(style, bubble);
    document.documentElement.append(this.host);
    this.refresh();
    this.timer = window.setInterval(() => this.refresh(), 1000);
    window.addEventListener('pagehide', () => { window.clearInterval(this.timer); this.host.remove(); }, { once: true });
  }

  private refresh(): void {
    const status = this.collector.status();
    this.count.textContent = String(status.totalObservationCount);
    this.host.setAttribute('aria-label', `${status.totalObservationCount} visible cards captured; ${status.state.toLowerCase().replace('_', ' ')}`);
  }
}

export default defineContentScript({
  matches: ['https://x.com/*'],
  runAt: 'document_idle',
  allFrames: false,
  noScriptStartedPostMessage: true,
  main() {
    const collector = new LiveCollector();
    void collector.ready().then(() => { new CounterBubble(collector); });
    browser.runtime.onMessage.addListener((message: unknown, sender, sendResponse) => {
      if (sender.id !== browser.runtime.id || !message || typeof message !== 'object' || !('type' in message)) return undefined;
      const command = message as CollectorCommand;
      void collector.ready().then(async () => {
        switch (command.type) {
          case 'XFI_STATUS': sendResponse(collector.messageStatus()); break;
          case 'XFI_START': sendResponse(await collector.start()); break;
          case 'XFI_SCROLL_START': sendResponse(collector.startScroll()); break;
          case 'XFI_SCROLL_STOP': sendResponse(collector.stopScroll()); break;
          case 'XFI_STOP': sendResponse(await collector.stop()); break;
          case 'XFI_EXPORT': sendResponse(await collector.exportPacket()); break;
          case 'XFI_EXPORT_CHUNK': sendResponse(collector.exportChunk(command.exportId, command.index)); break;
          case 'XFI_EXPORT_RELEASE': sendResponse(collector.releaseExport(command.exportId)); break;
          case 'XFI_ROLLOVER_COMPLETE': sendResponse(await collector.completeRollover(command.sessionId)); break;
          case 'XFI_DISCARD': sendResponse(await collector.discard()); break;
          default: return;
        }
      }).catch(() => sendResponse({ ok: false, status: collector.status(), error: 'COLLECTOR_COMMAND_FAILED' }));
      return true;
    });
  },
});
