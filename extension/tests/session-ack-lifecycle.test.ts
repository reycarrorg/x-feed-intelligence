import { beforeEach, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => ({ sendMessage: vi.fn() }));
vi.mock('wxt/browser', () => ({ browser: { runtime: { id: 'test-extension', sendMessage: mocks.sendMessage,
  onMessage: { addListener: vi.fn() } } } }));

beforeEach(() => {
  vi.resetModules();
  vi.clearAllMocks();
  vi.stubGlobal('defineContentScript', (definition: unknown) => definition);
  vi.stubGlobal('location', new URL('https://x.com/home'));
  Object.defineProperty(document, 'visibilityState', { configurable: true, value: 'visible' });
  document.body.innerHTML = '';
});

it('does not report Start or Stop as committed until each storage acknowledgment arrives', async () => {
  const releases: Array<() => void> = [];
  mocks.sendMessage.mockImplementation((message: { type: string }) => {
    if (message.type === 'XFI_SESSION_READ') return Promise.resolve({ snapshot: null });
    if (message.type === 'XFI_SESSION_WRITE') return new Promise((resolve) => releases.push(() => resolve({ ok: true })));
    return Promise.resolve({ ok: true });
  });
  const { LiveCollector } = await import('../entrypoints/collector.content');
  const collector = new LiveCollector();
  await collector.ready();

  const starting = collector.start();
  expect(collector.status()).toMatchObject({ state: 'ARMED', pendingState: 'CAPTURING', observationCount: 0 });
  let startReturned = false;
  void starting.then(() => { startReturned = true; });
  await Promise.resolve();
  expect(startReturned).toBe(false);
  releases.shift()!();
  expect((await starting).ok).toBe(true);
  expect(collector.status()).toMatchObject({ state: 'CAPTURING', pendingState: null });

  const stopping = collector.stop();
  expect(collector.status()).toMatchObject({ state: 'CAPTURING', pendingState: 'STOPPED' });
  let stopReturned = false;
  void stopping.then(() => { stopReturned = true; });
  await Promise.resolve();
  expect(stopReturned).toBe(false);
  releases.shift()!();
  expect((await stopping).ok).toBe(true);
  expect(collector.status()).toMatchObject({ state: 'STOPPED', pendingState: null });
});
