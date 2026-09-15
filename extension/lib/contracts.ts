export const COLLECTOR_VERSION = 'hybrid-extension-0.3.0';
export const PARSER_VERSION = 'visible-x-dom-0.3.0';
export const EXACT_ORIGIN = 'https://x.com';

export const LIMITS = Object.freeze({
  minimumVisibilityRatio: 0.5,
  maxCandidates: 100,
  maxDurationSeconds: 900,
  maxPacketBytes: 5_242_880,
  maxEvents: 256,
  maxAmbiguityRatio: 0.05,
});

export type LifecycleState =
  | 'INACTIVE'
  | 'ARMED'
  | 'CAPTURING'
  | 'PAUSED_HIDDEN'
  | 'LIMIT_REACHED'
  | 'STOPPED'
  | 'ERROR';

export type PromotionStatus = 'organic' | 'promoted' | 'ambiguous';

export interface CollectorStatus {
  state: LifecycleState;
  observationCount: number;
  organicCount: number;
  promotedCount: number;
  ambiguousCount: number;
  hardStopCode: string | null;
  startedAt: string | null;
  elapsedSeconds: number;
  autoScroll: false;
  networkRequests: 0;
  accountActions: 0;
}

export type CollectorCommand =
  | { type: 'XFI_STATUS' }
  | { type: 'XFI_START' }
  | { type: 'XFI_STOP' }
  | { type: 'XFI_EXPORT' }
  | { type: 'XFI_DISCARD' };

export interface CollectorResponse {
  ok: boolean;
  status: CollectorStatus;
  packet?: Record<string, unknown>;
  error?: string;
}
