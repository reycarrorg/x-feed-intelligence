import { expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => ({ addListener: vi.fn() }));

vi.mock('wxt/browser', () => ({
  browser: { runtime: { id: 'test-extension', sendMessage: vi.fn(async () => ({ snapshot: null })), onMessage: { addListener: mocks.addListener } } },
}));

it('responds to popup commands through the callback on Chromium and ignores other senders', async () => {
  vi.stubGlobal('defineContentScript', (definition: { main: () => void }) => {
    definition.main();
    return definition;
  });
  try {
    await import('../entrypoints/collector.content');
    const listener = mocks.addListener.mock.calls[0]?.[0];
    expect(listener).toBeTypeOf('function');

    const respond = vi.fn();
    expect(listener({ type: 'XFI_STATUS' }, { id: 'test-extension' }, respond)).toBe(true);
    await vi.waitFor(() => expect(respond).toHaveBeenCalledWith(expect.objectContaining({
      ok: true,
      status: expect.objectContaining({ state: 'ARMED' }),
    })));

    respond.mockClear();
    expect(listener({ type: 'XFI_STATUS' }, { id: 'another-extension' }, respond)).toBeUndefined();
    expect(respond).not.toHaveBeenCalled();

    expect(listener({ type: 'XFI_EXPORT' }, { id: 'test-extension' }, respond)).toBe(true);
    await vi.waitFor(() => expect(respond).toHaveBeenCalledWith(expect.objectContaining({
      ok: false,
      error: 'NOTHING_TO_EXPORT',
    })));
  } finally {
    vi.unstubAllGlobals();
  }
});
