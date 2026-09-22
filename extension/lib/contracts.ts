export const COLLECTOR_VERSION = 'hybrid-extension-0.6.0';
export const PARSER_VERSION = 'visible-x-dom-0.4.0';
export const EXACT_ORIGIN = 'https://x.com';

export const LIMITS = Object.freeze({
  minimumVisibilityRatio: 0.5,
  maxCandidates: 10_000,
  maxDurationSeconds: 28_800,
  maxPacketBytes: 15 * 1_048_576,
  // Firefox session storage is intentionally memory-only and has a smaller quota
  // than the export packet. Stop before this boundary so refresh recovery is real.
  maxRefreshRecoveryBytes: 9 * 1_048_576,
  maxEvents: 256,
  maxAmbiguityRatio: 0.05,
});

export type LifecycleState =
  | 'INACTIVE'
  | 'ARMED'
  | 'CAPTURING'
  | 'ROLLING_OVER'
  | 'PAUSED_HIDDEN'
  | 'LIMIT_REACHED'
  | 'STOPPED'
  | 'ERROR';

export type PromotionStatus = 'organic' | 'promoted' | 'ambiguous';

export interface CollectorStatus {
  state: LifecycleState;
  // Only acknowledged session-storage data contributes to the displayed totals.
  pendingState: LifecycleState | null;
  pendingObservationCount: number;
  pendingChanges: boolean;
  pendingPersistenceFailure: boolean;
  observationCount: number;
  totalObservationCount: number;
  partNumber: number;
  organicCount: number;
  promotedCount: number;
  ambiguousCount: number;
  hardStopCode: string | null;
  startedAt: string | null;
  elapsedSeconds: number;
  autoScroll: boolean;
  scrollPauseReason: string | null;
  networkRequests: 0;
  accountActions: 0;
}

// Kept by the extension background for a tab's lifetime so a normal x.com
// document refresh can reconnect without retaining a promise across Firefox
// restarts.  It deliberately never includes cookies, tokens, or page HTML.
export interface CollectorSessionSnapshot {
  revision: number;
  state: LifecycleState;
  observations: Array<Record<string, unknown>>;
  events: Array<{ event_code: string; at: string; safe_detail_code: string | null }>;
  sessionId: string | null;
  startedAt: number | null;
  stoppedAt: number | null;
  stopCode: string | null;
  ambiguousCount: number;
  promotionCounts: { organic: number; promoted: number; ambiguous: number };
  observationBytes: number;
  completedCount?: number;
  partNumber?: number;
  completedPromotionCounts?: { organic: number; promoted: number; ambiguous: number };
  completedAmbiguousCount?: number;
  stopAfterRollover?: boolean;
  assistedEver: boolean;
  scrollPauseReason: string | null;
}

export type CollectorCommand =
  | { type: 'XFI_STATUS' }
  | { type: 'XFI_START' }
  | { type: 'XFI_SCROLL_START' }
  | { type: 'XFI_SCROLL_STOP' }
  | { type: 'XFI_STOP' }
  | { type: 'XFI_EXPORT' }
  | { type: 'XFI_EXPORT_CHUNK'; exportId: string; index: number }
  | { type: 'XFI_EXPORT_RELEASE'; exportId: string }
  | { type: 'XFI_ROLLOVER_COMPLETE'; sessionId: string }
  | { type: 'XFI_DISCARD' };

export interface CollectorResponse {
  ok: boolean;
  status: CollectorStatus;
  export?: { id: string; sessionId: string; chunkCount: number; totalBytes: number };
  chunk?: string;
  error?: string;
}
