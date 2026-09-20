export const COLLECTOR_VERSION = 'hybrid-extension-0.4.0';
export const PARSER_VERSION = 'visible-x-dom-0.3.0';
export const EXACT_ORIGIN = 'https://x.com';

export const LIMITS = Object.freeze({
  minimumVisibilityRatio: 0.5,
  maxCandidates: 10_000,
  maxDurationSeconds: 28_800,
  maxPacketBytes: 134_217_728,
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
  | { type: 'XFI_EXPORT_CHUNK'; exportId: string; index: number }
  | { type: 'XFI_EXPORT_RELEASE'; exportId: string }
  | { type: 'XFI_DISCARD' };

export interface CollectorResponse {
  ok: boolean;
  status: CollectorStatus;
  export?: { id: string; sessionId: string; chunkCount: number; totalBytes: number };
  chunk?: string;
  error?: string;
}
