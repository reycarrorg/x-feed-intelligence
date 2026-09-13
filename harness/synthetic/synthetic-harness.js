/* TEST ONLY — NON-DISTRIBUTABLE. Reserved-origin synthetic harness. */
(function (global) {
  "use strict";

  const LIMITS = Object.freeze({minimumVisibilityRatio: 0.5, maxCandidates: 250, maxDurationMs: 1800000, maxPacketBytes: 5242880, maxAmbiguityRatio: 0.05});
  const HARD_STOPS = Object.freeze(["LOGIN_SURFACE", "CAPTCHA_OR_TURNSTILE", "RATE_LIMIT", "WRONG_ORIGIN", "PERMISSION_DRIFT", "UNKNOWN_TOPOLOGY", "AMBIGUITY_LIMIT", "QUEUE_LIMIT", "DURATION_LIMIT", "PACKET_LIMIT", "INJECTION_CONTENT", "ACCOUNT_ACTION_REQUEST"]);
  const RESERVED_ORIGIN = "https://fixture.example.invalid";

  function stableString(value) {
    if (value === null || typeof value !== "object") return JSON.stringify(value);
    if (Array.isArray(value)) return "[" + value.map(stableString).join(",") + "]";
    return "{" + Object.keys(value).sort().map((key) => JSON.stringify(key) + ":" + stableString(value[key])).join(",") + "}";
  }

  function containsInjection(text) {
    return /ignore (?:all |every |prior |previous )?(?:rules|instructions)|reveal (?:any )?(?:secret|token|password)|(?:visit|browse|open) https?:\/\/|follow this|run (?:this )?(?:command|code)/i.test(text || "");
  }

  class Harness {
    constructor(clock) {
      this.clock = clock || (() => Date.now());
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
      this.events.push({event_code: "SESSION_STARTED"});
      return true;
    }

    documentHidden() {
      if (this.state !== "CAPTURING") return false;
      this.state = "PAUSED_HIDDEN";
      this.events.push({event_code: "PAUSED_DOCUMENT_HIDDEN"});
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
      if (this.clock() - this.startedAt > LIMITS.maxDurationMs) return this.hardStop("DURATION_LIMIT");
      if (item.accountActionRequested) return this.hardStop("ACCOUNT_ACTION_REQUEST");
      if (containsInjection(item.visibleText)) return this.hardStop("INJECTION_CONTENT");
      if (item.topology !== "reviewed-v1" || item.topLevel !== true) return this.hardStop("UNKNOWN_TOPOLOGY");
      if (item.ambiguityRatio > LIMITS.maxAmbiguityRatio) return this.hardStop("AMBIGUITY_LIMIT");
      if (item.documentVisible !== true || item.visibilityRatio < LIMITS.minimumVisibilityRatio) return false;
      if (this.queue.length >= LIMITS.maxCandidates) return this.hardStop("QUEUE_LIMIT");
      const signature = stableString({identity: item.identity, visibleText: item.visibleText, promotion: item.promotion, relationships: item.relationships || []});
      const previous = this.identities[item.nodeKey];
      if (previous && previous.identity === item.identity) {
        previous.signature = signature;
        return false;
      }
      this.identities[item.nodeKey] = {identity: item.identity, signature: signature};
      this.domReferenceCount = Object.keys(this.identities).length;
      const record = {identity: item.identity, visible_text: item.visibleText, promotion: item.promotion, relationships: item.relationships || [], visibility_ratio: item.visibilityRatio};
      if (stableString({records: this.queue.concat([record])}).length > LIMITS.maxPacketBytes) return this.hardStop("PACKET_LIMIT");
      this.queue.push(record);
      this.events.push({event_code: "OBSERVATION_ACCEPTED"});
      return true;
    }

    userExport() {
      if (!["CAPTURING", "PAUSED_HIDDEN", "STOPPED"].includes(this.state)) return null;
      return {schema_version: "1.0.0", origin: RESERVED_ORIGIN, records: this.queue.slice(), effects: Object.assign({}, this.effects)};
    }

    userStop() {
      if (!["ARMED", "CAPTURING", "PAUSED_HIDDEN"].includes(this.state)) return false;
      this.teardown();
      this.state = "STOPPED";
      this.events.push({event_code: "STOPPED_USER"});
      return true;
    }

    hardStop(code) {
      if (!HARD_STOPS.includes(code)) code = "UNKNOWN_TOPOLOGY";
      this.teardown();
      this.state = "ERROR";
      this.events.push({event_code: code});
      return false;
    }

    acknowledge() {
      if (this.state !== "ERROR") return false;
      this.state = "INACTIVE";
      this.queue = [];
      this.events = [];
      this.origin = null;
      return true;
    }

    teardown() {
      this.observerCount = 0;
      this.timerCount = 0;
      this.domReferenceCount = 0;
      this.identities = Object.create(null);
    }

    snapshot() {
      return {state: this.state, queueCount: this.queue.length, observerCount: this.observerCount, timerCount: this.timerCount, domReferenceCount: this.domReferenceCount, effects: Object.assign({}, this.effects), events: this.events.slice()};
    }
  }

  global.XFIHarness = Object.freeze({Harness, LIMITS, HARD_STOPS, RESERVED_ORIGIN, stableString});

  if (typeof chrome !== "undefined" && chrome.runtime && chrome.runtime.onMessage) {
    const runtime = new Harness();
    let intersections = null;
    let mutations = null;
    let nextNodeKey = 0;
    const nodeKeys = new WeakMap();

    function nodeKey(card) {
      if (!nodeKeys.has(card)) nodeKeys.set(card, "fixture-node-" + (++nextNodeKey));
      return nodeKeys.get(card);
    }

    function visibleText(node) {
      if (!node || node.getClientRects().length === 0) return null;
      const style = global.getComputedStyle(node);
      if (style.display === "none" || style.visibility === "hidden" || Number(style.opacity) === 0) return null;
      return node.textContent;
    }

    function parseCard(card, ratio) {
      const author = visibleText(card.querySelector("[data-fixture-author]"));
      const text = visibleText(card.querySelector("[data-fixture-text]"));
      const promotion = visibleText(card.querySelector("[data-fixture-promotion]"));
      const identity = card.getAttribute("data-fixture-card");
      return {
        origin: global.location.origin,
        nodeKey: nodeKey(card),
        identity: identity,
        visibleText: [author, text, promotion].filter(Boolean).join("\n"),
        promotion: promotion === "Promoted" ? "promoted" : (promotion === "Review required" ? "ambiguous" : "organic"),
        relationships: [],
        topology: identity && author && text ? "reviewed-v1" : "unknown",
        topLevel: card.parentElement === document.body || card.parentElement.hasAttribute("data-fixture-feed"),
        ambiguityRatio: card.hasAttribute("data-fixture-ambiguous") ? Number(card.getAttribute("data-fixture-ambiguous")) : 0,
        documentVisible: document.visibilityState === "visible",
        visibilityRatio: ratio,
      };
    }

    function inspectStops() {
      const stop = document.querySelector("[data-fixture-stop]");
      if (stop) runtime.hardStop(stop.getAttribute("data-fixture-stop"));
    }

    function observeCard(card) {
      if (intersections && card instanceof Element && card.matches("article[data-fixture-card]")) intersections.observe(card);
    }

    function attach() {
      if (intersections || mutations || document.visibilityState !== "visible") return;
      inspectStops();
      if (runtime.state !== "CAPTURING") return;
      intersections = new IntersectionObserver((entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) runtime.candidate(parseCard(entry.target, entry.intersectionRatio));
          if (runtime.state === "ERROR") detach();
        }
      }, {threshold: [LIMITS.minimumVisibilityRatio]});
      mutations = new MutationObserver((entries) => {
        inspectStops();
        for (const entry of entries) {
          for (const node of entry.addedNodes) {
            if (!(node instanceof Element)) continue;
            observeCard(node);
            node.querySelectorAll("article[data-fixture-card]").forEach(observeCard);
          }
          if (entry.target instanceof Element) observeCard(entry.target.closest("article[data-fixture-card]"));
        }
        if (runtime.state === "ERROR") detach();
      });
      document.querySelectorAll("article[data-fixture-card]").forEach(observeCard);
      mutations.observe(document.documentElement, {childList: true, subtree: true, characterData: true, attributes: true, attributeFilter: ["data-fixture-card", "data-fixture-stop", "data-fixture-ambiguous"]});
    }

    function detach() {
      if (intersections) intersections.disconnect();
      if (mutations) mutations.disconnect();
      intersections = null;
      mutations = null;
      runtime.teardown();
    }

    document.addEventListener("visibilitychange", () => {
      if (document.visibilityState === "hidden") { runtime.documentHidden(); detach(); }
      else if (runtime.documentVisible()) attach();
    });

    chrome.runtime.onMessage.addListener((message, _sender, respond) => {
      let result = false;
      if (message && message.action === "USER_ARM") result = runtime.userArm(global.location.origin);
      else if (message && message.action === "USER_START") { result = runtime.userStart(); if (result) attach(); }
      else if (message && message.action === "USER_STOP") { result = runtime.userStop(); detach(); }
      else if (message && message.action === "USER_EXPORT") result = runtime.userExport();
      else if (message && message.action === "ACKNOWLEDGE") result = runtime.acknowledge();
      respond({result, snapshot: runtime.snapshot()});
      return false;
    });
  }
})(globalThis);
