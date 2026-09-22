import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';

describe('popup width contract', () => {
  it('keeps a 390px minimum action-popup width instead of clamping to a narrow host viewport', () => {
    const css = readFileSync('entrypoints/popup/style.css', 'utf8');
    expect(css).toContain('width: 390px');
    expect(css).toContain('min-width: 390px');
    expect(css).not.toContain('max-width: 100vw');
  });
});
