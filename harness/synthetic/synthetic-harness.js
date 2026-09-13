/* TEST ONLY — NON-DISTRIBUTABLE. Reserved-origin synthetic harness. */
(function (global) {
  "use strict";

  const LIMITS = Object.freeze({minimumVisibilityRatio: 0.5, maxCandidates: 250, maxDurationMs: 1800000, maxPacketBytes: 5242880, maxAmbiguityRatio: 0.05});
  const HARD_STOPS = Object.freeze(["LOGIN_SURFACE", "SIGN_OUT_STATE", "ACCOUNT_LOCK", "CAPTCHA_OR_TURNSTILE", "VERIFICATION_CHALLENGE", "UNUSUAL_ACTIVITY", "CONSENT_SURFACE", "RATE_LIMIT", "WRONG_ORIGIN", "IFRAME_BOUNDARY", "PERMISSION_DRIFT", "PARSER_VERSION_MISMATCH", "UNKNOWN_TOPOLOGY", "AMBIGUITY_LIMIT", "QUEUE_LIMIT", "DURATION_LIMIT", "PACKET_LIMIT", "DISK_OR_MEMORY_LIMIT", "RETENTION_FAILURE", "SCHEMA_MISMATCH", "EXCLUDED_PERMISSION_REQUEST", "ACCOUNT_ACTION_REQUEST", "INJECTION_CONTENT"]);
  const RESERVED_ORIGIN = "https://fixture.example.invalid";

  function stableString(value) {
    if (value === null || typeof value !== "object") return JSON.stringify(value);
    if (Array.isArray(value)) return "[" + value.map(stableString).join(",") + "]";
    return "{" + Object.keys(value).sort().map((key) => JSON.stringify(key) + ":" + stableString(value[key])).join(",") + "}";
  }

  function utf8Bytes(value) {
    if (typeof TextEncoder !== "undefined") return new TextEncoder().encode(value).length;
    let count = 0;
    for (let index = 0; index < value.length; index += 1) {
      const code = value.charCodeAt(index);
      if (code < 0x80) count += 1;
      else if (code < 0x800) count += 2;
      else if (code >= 0xD800 && code <= 0xDBFF && index + 1 < value.length && value.charCodeAt(index + 1) >= 0xDC00 && value.charCodeAt(index + 1) <= 0xDFFF) { count += 4; index += 1; }
      else count += 3;
    }
    return count;
  }

  function iso(value) { return new Date(value).toISOString(); }

  function containsInjection(text) {
    return /ignore (?:all |every |prior |previous )?(?:rules|instructions)|reveal (?:any )?(?:secret|token|password)|(?:visit|browse|open) https?:\/\/|follow this|run (?:this )?(?:command|code)/i.test(text || "");
  }

  class Harness {
    constructor(clock, timerApi, durationMs) {
      this.clock = clock || (() => Date.now());
      this.timerApi = timerApi || null;
      this.durationMs = Math.max(1, Math.min(LIMITS.maxDurationMs, Number(durationMs) || LIMITS.maxDurationMs));
      this.timerToken = null;
      this.state = "INACTIVE";
      this.queue = [];
      this.events = [];
      this.identities = Object.create(null);
      this.observerCount = 0;
      this.timerCount = 0;
      this.domReferenceCount = 0;
      this.startedAt = null;
      this.origin = null;
      this.effects = {network_requests: 0, account_actions: 0, automated_input_events: 0, cookie_reads: 0, header_reads: 0, page_storage_reads: 0, hidden_data_reads: 0, page_world_injections: 0};
    }

    event(code) { this.events.push({event_code: code, at: iso(this.clock()), safe_detail_code: null}); }

    userArm(origin) {
      if (this.state !== "INACTIVE") return false;
      if (origin !== RESERVED_ORIGIN) return this.hardStop("WRONG_ORIGIN");
      this.origin = origin;
      this.state = "ARMED";
      return true;
    }

    userStart() {
      if (this.state !== "ARMED") return false;
      this.state = "CAPTURING";
      this.startedAt = this.clock();
      this.observerCount = 2;
      this.timerCount = 1;
      this.event("SESSION_STARTED");
      if (this.timerApi) this.timerToken = this.timerApi.set(() => this.hardStop("DURATION_LIMIT"), this.durationMs);
      return true;
    }

    documentHidden() {
      if (this.state !== "CAPTURING") return false;
      this.state = "PAUSED_HIDDEN";
      this.event("PAUSED_DOCUMENT_HIDDEN");
      return true;
    }

    documentVisible() {
      if (this.state !== "PAUSED_HIDDEN") return false;
      this.state = "CAPTURING";
      return true;
    }

    candidate(item) {
      if (this.state !== "CAPTURING") return false;
      if (item.origin !== RESERVED_ORIGIN) return this.hardStop("WRONG_ORIGIN");
      if (this.clock() - this.startedAt >= this.durationMs) return this.hardStop("DURATION_LIMIT");
      if (item.accountActionRequested) return this.hardStop("ACCOUNT_ACTION_REQUEST");
      if (containsInjection(item.visibleText)) return this.hardStop("INJECTION_CONTENT");
      if (item.topology !== "reviewed-v1" || item.topLevel !== true) return this.hardStop("UNKNOWN_TOPOLOGY");
      if (item.ambiguityRatio > LIMITS.maxAmbiguityRatio) return this.hardStop("AMBIGUITY_LIMIT");
      if (item.documentVisible !== true || item.visibilityRatio < LIMITS.minimumVisibilityRatio) return false;
      const signature = stableString({identity: item.identity, visibleText: item.visibleText, authorLabel: item.authorLabel || null, promotion: item.promotion, relationships: item.relationships || []});
      const previous = this.identities[item.nodeKey];
      if (previous && previous.identity === item.identity && previous.signature === signature) return false;
      if (this.queue.length >= LIMITS.maxCandidates) return this.hardStop("QUEUE_LIMIT");
      const record = {identity: item.identity, visible_text: item.visibleText, author_label: item.authorLabel || "Unknown", promotion: item.promotion, relationships: item.relationships || [], visibility_ratio: item.visibilityRatio, observed_at: iso(this.clock())};
      if (utf8Bytes(stableString({records: this.queue.concat([record])})) > LIMITS.maxPacketBytes) return this.hardStop("PACKET_LIMIT");
      this.identities[item.nodeKey] = {identity: item.identity, signature};
      this.domReferenceCount = Object.keys(this.identities).length;
      this.queue.push(record);
      this.event("OBSERVATION_ACCEPTED");
      return true;
    }

    userExport() {
      if (!["CAPTURING", "PAUSED_HIDDEN", "STOPPED"].includes(this.state)) return null;
      return {records: this.queue.slice(), effects: Object.assign({}, this.effects), started_at: iso(this.startedAt === null ? this.clock() : this.startedAt), ended_at: iso(this.clock()), events: this.events.slice()};
    }

    userStop() {
      if (!["ARMED", "CAPTURING", "PAUSED_HIDDEN"].includes(this.state)) return false;
      this.teardown();
      this.state = "STOPPED";
      this.event("STOPPED_USER");
      return true;
    }

    userDiscard() {
      this.teardown();
      this.state = "INACTIVE";
      this.queue = [];
      this.events = [];
      this.origin = null;
      this.startedAt = null;
      return true;
    }

    hardStop(code) {
      if (!HARD_STOPS.includes(code)) code = "UNKNOWN_TOPOLOGY";
      this.teardown();
      this.state = "ERROR";
      this.event(code);
      return false;
    }

    acknowledge() { return this.state === "ERROR" ? this.userDiscard() : false; }

    teardown() {
      if (this.timerApi && this.timerToken !== null) this.timerApi.clear(this.timerToken);
      this.timerToken = null;
      this.observerCount = 0;
      this.timerCount = 0;
      this.domReferenceCount = 0;
      this.identities = Object.create(null);
    }

    snapshot() {
      return {state: this.state, queueCount: this.queue.length, observerCount: this.observerCount, timerCount: this.timerCount, domReferenceCount: this.domReferenceCount, effects: Object.assign({}, this.effects), events: this.events.slice()};
    }
  }

  global.XFIHarness = Object.freeze({Harness, LIMITS, HARD_STOPS, RESERVED_ORIGIN, stableString, utf8Bytes});

  if (typeof chrome !== "undefined" && chrome.runtime && chrome.runtime.onMessage) {
    const configuredDuration = Number(document.querySelector("[data-fixture-max-duration-ms]")?.getAttribute("data-fixture-max-duration-ms"));
    const runtime = new Harness(() => Date.now(), {set: (callback, delay) => global.setTimeout(callback, delay), clear: (token) => global.clearTimeout(token)}, configuredDuration);
    global.__XFI_TEST_SNAPSHOT__ = () => runtime.snapshot();
    let intersections = null;
    let mutations = null;
    let nextNodeKey = 0;
    const nodeKeys = new WeakMap();
    const intersectionRatios = new WeakMap();

    function nodeKey(card) {
      if (!nodeKeys.has(card)) nodeKeys.set(card, "fixture-node-" + (++nextNodeKey));
      return nodeKeys.get(card);
    }

    function elementVisible(element, root) {
      for (let current = element; current; current = current.parentElement) {
        const style = global.getComputedStyle(current);
        if (current.hidden || current.getAttribute("aria-hidden") === "true" || style.display === "none" || style.visibility === "hidden" || Number(style.opacity) === 0) return false;
        if (current === root) break;
      }
      const rectangles = element.getClientRects();
      if (!rectangles.length) return false;
      return Array.from(rectangles).some((rect) => rect.width > 0 && rect.height > 0 && rect.bottom > 0 && rect.right > 0 && rect.top < global.innerHeight && rect.left < global.innerWidth);
    }

    function visibleText(root) {
      if (!root || !elementVisible(root, root)) return null;
      const chunks = [];
      const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
      for (let text = walker.nextNode(); text; text = walker.nextNode()) {
        if (text.nodeValue && text.nodeValue.trim() && text.parentElement && elementVisible(text.parentElement, root)) chunks.push(text.nodeValue.trim());
      }
      return chunks.join(" ").replace(/\s+/g, " ").trim() || null;
    }

    function parseCard(card, ratio) {
      const author = visibleText(card.querySelector("[data-fixture-author]"));
      const text = visibleText(card.querySelector("[data-fixture-text]"));
      const promotion = visibleText(card.querySelector("[data-fixture-promotion]"));
      const identity = card.getAttribute("data-fixture-card");
      const relationKind = card.getAttribute("data-fixture-relationship-kind");
      const relationSource = card.getAttribute("data-fixture-source-id");
      return {
        origin: global.location.origin, nodeKey: nodeKey(card), identity, authorLabel: author, visibleText: text,
        promotion: promotion === "Promoted" ? "promoted" : (promotion === "Review required" ? "ambiguous" : "organic"),
        relationships: relationKind && relationSource ? [{kind: relationKind, source_identity: relationSource}] : [],
        topology: identity && author && text ? "reviewed-v1" : "unknown",
        topLevel: Boolean(card.parentElement && card.parentElement.hasAttribute("data-fixture-feed")),
        ambiguityRatio: card.hasAttribute("data-fixture-ambiguous") ? Number(card.getAttribute("data-fixture-ambiguous")) : 0,
        documentVisible: document.visibilityState === "visible", visibilityRatio: ratio,
      };
    }

    function inspectStops() {
      const stop = document.querySelector("[data-fixture-stop]");
      if (stop) runtime.hardStop(stop.getAttribute("data-fixture-stop"));
    }

    function processCard(card) {
      if (!(card instanceof Element) || !card.matches("article[data-fixture-card]")) return;
      const ratio = intersectionRatios.get(card) || 0;
      if (ratio >= LIMITS.minimumVisibilityRatio) runtime.candidate(parseCard(card, ratio));
    }

    function observeCard(card) {
      if (intersections && card instanceof Element && card.matches("article[data-fixture-card]")) intersections.observe(card);
    }

    function closestCard(node) {
      const element = node instanceof Element ? node : node && node.parentElement;
      return element ? element.closest("article[data-fixture-card]") : null;
    }

    function attach() {
      if (intersections || mutations || document.visibilityState !== "visible") return;
      inspectStops();
      if (runtime.state !== "CAPTURING") return;
      intersections = new IntersectionObserver((entries) => {
        for (const entry of entries) {
          intersectionRatios.set(entry.target, entry.isIntersecting ? entry.intersectionRatio : 0);
          if (entry.isIntersecting) processCard(entry.target);
          if (runtime.state === "ERROR") detach();
        }
      }, {threshold: [0, LIMITS.minimumVisibilityRatio, 1]});
      mutations = new MutationObserver((entries) => {
        inspectStops();
        const changedCards = new Set();
        for (const entry of entries) {
          const targetCard = closestCard(entry.target);
          if (targetCard) changedCards.add(targetCard);
          for (const node of entry.addedNodes || []) {
            if (!(node instanceof Element)) continue;
            observeCard(node);
            node.querySelectorAll("article[data-fixture-card]").forEach(observeCard);
            const addedCard = closestCard(node);
            if (addedCard) changedCards.add(addedCard);
          }
        }
        changedCards.forEach(processCard);
        if (runtime.state === "ERROR") detach();
      });
      document.querySelectorAll("article[data-fixture-card]").forEach(observeCard);
      mutations.observe(document.documentElement, {childList: true, subtree: true, characterData: true, attributes: true, attributeFilter: ["class", "style", "hidden", "aria-hidden", "data-fixture-card", "data-fixture-stop", "data-fixture-ambiguous", "data-fixture-relationship-kind", "data-fixture-source-id"]});
    }

    function detach() {
      if (intersections) intersections.disconnect();
      if (mutations) mutations.disconnect();
      intersections = null;
      mutations = null;
      runtime.teardown();
    }

    async function buildEnvelope(capture) {
      const sessionId = "synthetic-dom-browser-001";
      const observations = capture.records.map((record, index) => {
        const provenanceId = sessionId + "-provenance-" + String(index).padStart(3, "0");
        const authorId = "synthetic-author-" + record.author_label.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
        const ambiguous = record.promotion === "ambiguous";
        return {
          observation_id: sessionId + "-observation-" + String(index).padStart(3, "0"), session_id: sessionId, appearance_index: index, top_level: true,
          visibility_ratio: record.visibility_ratio, document_visible: true, platform_post_id: record.identity, canonical_permalink: null, visible_text: record.visible_text, displayed_timestamp: "synthetic-visible-card",
          authors: [{local_author_id: authorId, platform_author_id: null, display_name: record.author_label, handle: null, role: record.relationships.some((item) => item.kind === "quotes") ? "quoting" : "original", identity_confidence: 1.0, uncertainty_codes: []}],
          relationships: record.relationships.map((item) => ({kind: item.kind, source_local_post_id: "synthetic-source-" + item.source_identity, source_platform_post_id: item.source_identity, confidence: 1.0, provenance_ids: [provenanceId]})), media: [],
          promotion: {status: record.promotion, evidence: [record.promotion === "promoted" ? "visible_label" : (ambiguous ? "layout_marker" : "none")], confidence: ambiguous ? 0.5 : 1.0},
          provenance: [{provenance_id: provenanceId, modality: "synthetic_dom", collector_version: "synthetic-mv3-0.2.0", parser_or_ocr_version: "synthetic-dom-reviewed-v1", field: "visible_text", observed_at: record.observed_at, video_time_ms: null, crop_xywh: null, confidence: ambiguous ? 0.5 : 1.0}],
          uncertainty: ambiguous ? [{code: "SYNTHETIC_AMBIGUOUS_PROMOTION", field: "promotion", severity: "review", requires_review: true, safe_detail: "Authored fixture requires review."}] : [],
          input_location: {viewport_time_ms: Math.max(0, new Date(record.observed_at).getTime() - new Date(capture.started_at).getTime()), video_time_ms: null, crop_xywh: null},
        };
      });
      const envelope = {schema_version: "1.0.0", session: {session_id: sessionId, schema_version: "1.0.0", source: "synthetic_dom", started_at: capture.started_at, ended_at: capture.ended_at, origin: RESERVED_ORIGIN, collector_version: "synthetic-mv3-0.2.0", privacy_profile: "default_local", limits: {max_candidates: 250, max_duration_seconds: 1800, max_packet_bytes: 5242880}}, observations, collection_events: capture.events, content_digest: ""};
      const digestSource = Object.assign({}, envelope);
      delete digestSource.content_digest;
      const bytes = new TextEncoder().encode(stableString(digestSource));
      const hash = await crypto.subtle.digest("SHA-256", bytes);
      envelope.content_digest = "sha256:" + Array.from(new Uint8Array(hash), (byte) => byte.toString(16).padStart(2, "0")).join("");
      if (utf8Bytes(stableString(envelope)) > LIMITS.maxPacketBytes) runtime.hardStop("PACKET_LIMIT");
      return envelope;
    }

    document.addEventListener("visibilitychange", () => {
      if (document.visibilityState === "hidden") { runtime.documentHidden(); detach(); }
      else if (runtime.documentVisible()) attach();
    });

    chrome.runtime.sendMessage({kind: "XFI_REGISTER_FIXTURE"});
    chrome.runtime.onMessage.addListener((message, _sender, respond) => {
      if (!message || !message.action) { respond({result: false, snapshot: runtime.snapshot()}); return false; }
      if (message.action === "USER_EXPORT") {
        const capture = runtime.userExport();
        if (!capture) { respond({result: null, snapshot: runtime.snapshot()}); return false; }
        buildEnvelope(capture).then((result) => respond({result, snapshot: runtime.snapshot()}), () => { runtime.hardStop("SCHEMA_MISMATCH"); respond({result: null, snapshot: runtime.snapshot()}); });
        return true;
      }
      let result = false;
      if (message.action === "USER_ARM") result = runtime.userArm(global.location.origin);
      else if (message.action === "USER_START") { result = runtime.userStart(); if (result) attach(); }
      else if (message.action === "USER_STOP") { result = runtime.userStop(); detach(); }
      else if (message.action === "USER_DISCARD") { result = runtime.userDiscard(); detach(); }
      else if (message.action === "ACKNOWLEDGE") { result = runtime.acknowledge(); detach(); }
      respond({result, snapshot: runtime.snapshot()});
      return false;
    });
  }
})(globalThis);
