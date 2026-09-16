import { beforeEach, describe, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => ({
  getLastFocused: vi.fn(),
  query: vi.fn(),
  contains: vi.fn(),
  sendMessage: vi.fn(),
  request: vi.fn(),
  remove: vi.fn(),
}));

vi.mock('wxt/browser', () => ({
  browser: {
    windows: { getLastFocused: mocks.getLastFocused },
    tabs: { query: mocks.query, sendMessage: mocks.sendMessage },
    permissions: { contains: mocks.contains, request: mocks.request, remove: mocks.remove },
  },
}));

const status = {
  state: 'ARMED', observationCount: 0, organicCount: 0, promotedCount: 0,
  ambiguousCount: 0, hardStopCode: null, startedAt: null, elapsedSeconds: 0,
  autoScroll: false, networkRequests: 0, accountActions: 0,
};

beforeEach(() => {
  vi.resetModules();
  vi.clearAllMocks();
  document.body.innerHTML = `
    <span id="state"></span><p id="message"></p>
    <strong id="total"></strong><strong id="organic"></strong>
    <strong id="promoted"></strong><strong id="ambiguous"></strong>
    <button id="arm"></button><button id="start"></button>
    <button id="stop"></button><button id="export"></button>
    <button id="discard"></button><button id="revoke"></button>
  `;
  mocks.getLastFocused.mockResolvedValue({ id: 42, type: 'normal' });
  mocks.contains.mockResolvedValue(true);
  mocks.sendMessage.mockResolvedValue({ ok: true, status });
});

describe('popup target tab', () => {
  it('uses the active tab of the last focused normal window and confirms its own X collector even without URL metadata', async () => {
    mocks.query.mockResolvedValue([{ id: 7 }]);

    await import('../entrypoints/popup/main');
    await vi.waitFor(() => expect(document.querySelector('#message')?.textContent).toContain('Ready.'));

    expect(mocks.getLastFocused).toHaveBeenCalledWith({ windowTypes: ['normal'] });
    expect(mocks.query).toHaveBeenCalledWith({ active: true, windowId: 42 });
    expect(mocks.sendMessage).toHaveBeenCalledWith(7, { type: 'XFI_STATUS' });
    expect((document.querySelector('#start') as HTMLButtonElement).disabled).toBe(false);
  });

  it('keeps collection disabled when the active tab has no X collector', async () => {
    mocks.query.mockResolvedValue([{ id: 8 }]);
    mocks.sendMessage.mockRejectedValue(new Error('Receiving end does not exist'));

    await import('../entrypoints/popup/main');
    await vi.waitFor(() => expect(document.querySelector('#message')?.textContent).toContain('No X collector is loaded'));

    expect(mocks.sendMessage).toHaveBeenCalledWith(8, { type: 'XFI_STATUS' });
    expect((document.querySelector('#start') as HTMLButtonElement).disabled).toBe(true);
  });

  it('offers exact X access without trusting unavailable tab URL metadata or starting capture', async () => {
    mocks.query.mockResolvedValue([{ id: 7 }]);
    mocks.contains.mockResolvedValue(false);
    mocks.request.mockResolvedValue(true);

    await import('../entrypoints/popup/main');
    await vi.waitFor(() => expect(document.querySelector('#message')?.textContent).toContain('X access is off'));
    const arm = document.querySelector('#arm') as HTMLButtonElement;
    expect(arm.disabled).toBe(false);
    arm.click();
    await vi.waitFor(() => expect(mocks.request).toHaveBeenCalledWith({ origins: ['https://x.com/*'] }));
    expect(mocks.sendMessage).not.toHaveBeenCalled();
    expect((document.querySelector('#start') as HTMLButtonElement).disabled).toBe(true);
  });
});
