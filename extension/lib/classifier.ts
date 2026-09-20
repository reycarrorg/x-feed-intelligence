/**
 * A deliberately conservative, explainable first pass inspired by Feed Cleaner's
 * transparent grading UX. No Feed Cleaner source is copied because its repository
 * did not include a complete root license grant when reviewed.
 */

export interface PreviewGrade {
  grade: 'A' | 'B' | 'C' | 'D' | 'E' | 'F';
  reasons: string[];
  needsReview: boolean;
}

const INJECTION_PATTERNS = [
  /ignore (?:all |every |prior |previous )?(?:rules|instructions)/i,
  /reveal (?:any )?(?:secret|token|password|credential)/i,
  /(?:run|execute) (?:this )?(?:command|script|code)/i,
  /(?:visit|browse|open) https?:\/\//i,
  /follow this account/i,
];

const LOW_SIGNAL_PATTERNS = [
  /\b(?:game[- ]?changer|mind[- ]?blowing|insane|unlimited|secret hack)\b/i,
  /\b(?:comment|reply) ["“']?(?:yes|guide|link)["”']?\b/i,
  /\b(?:don't miss|act now|limited time)\b/i,
];

const EVIDENCE_PATTERNS = [
  /https?:\/\//i,
  /\b(?:github|paper|documentation|benchmark|release notes|source|dataset)\b/i,
  /\b(?:because|measured|tested|reproduced|limitation|tradeoff)\b/i,
];

export function containsPromptInjection(text: string): boolean {
  return INJECTION_PATTERNS.some((pattern) => pattern.test(text));
}

export function previewGrade(text: string | null, promoted: boolean): PreviewGrade {
  if (promoted) return { grade: 'F', reasons: ['promoted content is excluded from organic grading'], needsReview: false };
  if (!text || text.trim().length < 12) return { grade: 'F', reasons: ['not enough visible text'], needsReview: true };
  if (containsPromptInjection(text)) return { grade: 'E', reasons: ['contains instruction-like or prompt-injection text'], needsReview: true };

  const reasons: string[] = [];
  const evidence = EVIDENCE_PATTERNS.filter((pattern) => pattern.test(text)).length;
  const lowSignal = LOW_SIGNAL_PATTERNS.filter((pattern) => pattern.test(text)).length;
  if (evidence) reasons.push('contains inspectable evidence language or a source lead');
  if (lowSignal) reasons.push('contains promotional or engagement-bait language');
  if (text.length >= 240) reasons.push('contains substantive visible detail');

  if (evidence >= 2 && text.length >= 120 && lowSignal === 0) return { grade: 'B', reasons, needsReview: true };
  if (lowSignal >= 2 && evidence === 0) return { grade: 'D', reasons, needsReview: true };
  return { grade: 'C', reasons: reasons.length ? reasons : ['requires local analysis'], needsReview: true };
}
