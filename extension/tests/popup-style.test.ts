import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';

describe('popup width contract', () => {
  it('keeps a 390px minimum action-popup width instead of clamping to a narrow host viewport', () => {
    const css = readFileSync('entrypoints/popup/style.css', 'utf8');
    expect(css).toContain('width: 390px');
    expect(css).toContain('min-width: 390px');
    expect(css).not.toContain('max-width: 100vw');
  });

  it('exposes in-popup auto-scroll and default export-subfolder settings without a page overlay control', () => {
    const html = readFileSync('entrypoints/popup/index.html', 'utf8');
    expect(html).toContain('id="auto-scroll-setting"');
    expect(html).toContain('id="export-subfolder"');
    expect(html).toContain('value="XFI"');
    expect(html).not.toContain('Keep control on this X page');
  });
});
