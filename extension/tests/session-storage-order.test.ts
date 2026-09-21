import { beforeEach, describe, expect, it, vi } from 'vitest';
import { LIMITS, type CollectorSessionSnapshot } from '../lib/contracts';

type Listener = (message: unknown, sender: { id: string; tab: { id: number } }) => Promise<unknown> | undefined;
const mocks = vi.hoisted(() => ({
  listener: null as Listener | null,
  records: new Map<string, unknown>(),
  get: vi.fn(), set: vi.fn(), remove: vi.fn(),
}));

vi.mock('wxt/browser', () => ({ browser: {
  runtime: { id: 'test-extension', onMessage: { addListener: (listener: Listener) => { mocks.listener = listener; } } },
  storage: { session: { get: mocks.get, set: mocks.set, remove: mocks.remove },
    local: { get: vi.fn(async () => ({ xfi_owned_exports_v1: { nextSequence: 1, items: [] } })), set: vi.fn() } },
  downloads: { onChanged: { addListener: vi.fn() } },
  tabs: { onRemoved: { addListener: vi.fn() } },
} }));

const key = 'xfi_tab_session_v1_7';
const failedKey = 'xfi_tab_session_v1_failed_7';
const ownerKey = 'xfi_tab_session_v1_owner_7';
const sender = { id: 'test-extension', tab: { id: 7 } };
const snapshot = (revision: number, sessionId = 'session-a', state: CollectorSessionSnapshot['state'] = 'CAPTURING'): CollectorSessionSnapshot => ({
  revision, sessionId, state, observations: [{ observation_id: `post-${revision}` }], events: [],
  startedAt: 1, stoppedAt: state === 'STOPPED' ? 2 : null, stopCode: null,
  ambiguousCount: 0, promotionCounts: { organic: 1, promoted: 0, ambiguous: 0 },
  observationBytes: 20, assistedEver: false, scrollPauseReason: null,
});

async function loadBackground(): Promise<void> {
  vi.stubGlobal('defineBackground', (main: () => void) => { main(); return main; });
  await import('../entrypoints/background');
}
function send(message: unknown, clientId = 'test-document', documentStartedAt = 1000): Promise<any> {
  return mocks.listener!({ ...(message as object), clientId, documentStartedAt }, sender) as Promise<any>;
}
function deferred(): { promise: Promise<void>; resolve: () => void } {
  let resolve!: () => void;
  const promise = new Promise<void>((done) => { resolve = done; });
  return { promise, resolve };
}

beforeEach(() => {
  vi.resetModules();
  vi.clearAllMocks();
  mocks.records.clear();
  mocks.records.set(ownerKey, { clientId: 'test-document', documentStartedAt: 1000 });
  mocks.get.mockImplementation(async (keys: string | string[]) => Object.fromEntries(
    (Array.isArray(keys) ? keys : [keys]).filter((entry) => mocks.records.has(entry)).map((entry) => [entry, mocks.records.get(entry)])));
  mocks.set.mockImplementation(async (value: Record<string, unknown>) => { for (const [entry, item] of Object.entries(value)) mocks.records.set(entry, item); });
  mocks.remove.mockImplementation(async (keys: string | string[]) => { for (const entry of Array.isArray(keys) ? keys : [keys]) mocks.records.delete(entry); });
});

describe('tab session storage ordering', () => {
  it('serializes delayed writes and leaves the newest revision after completion', async () => {
    await loadBackground();
    const gate = deferred();
    let writes = 0;
    mocks.set.mockImplementation(async (value: Record<string, unknown>) => {
      if (++writes === 1) await gate.promise;
      for (const [entry, item] of Object.entries(value)) mocks.records.set(entry, item);
    });
    const first = send({ type: 'XFI_SESSION_WRITE', snapshot: snapshot(1) });
    await vi.waitFor(() => expect(writes).toBe(1));
    const second = send({ type: 'XFI_SESSION_WRITE', snapshot: snapshot(2, 'session-a', 'STOPPED') });
    await Promise.resolve();
    expect(writes).toBe(1);
    gate.resolve();
    expect(await first).toEqual({ ok: true });
    expect(await second).toEqual({ ok: true });
    expect((mocks.records.get(key) as CollectorSessionSnapshot).revision).toBe(2);
    expect((await send({ type: 'XFI_SESSION_READ' })).snapshot.state).toBe('STOPPED');
  });

  it('holds a recovery read behind a write already received by the background', async () => {
    await loadBackground();
    const gate = deferred();
    mocks.set.mockImplementationOnce(async (value: Record<string, unknown>) => {
      await gate.promise;
      for (const [entry, item] of Object.entries(value)) mocks.records.set(entry, item);
    });
    const writing = send({ type: 'XFI_SESSION_WRITE', snapshot: snapshot(1) });
    await vi.waitFor(() => expect(mocks.set).toHaveBeenCalledTimes(1));
    const reading = send({ type: 'XFI_SESSION_READ' });
    let readResolved = false;
    void reading.then(() => { readResolved = true; });
    await Promise.resolve();
    expect(readResolved).toBe(false);
    gate.resolve();
    expect(await writing).toEqual({ ok: true });
    expect(await reading).toMatchObject({ snapshot: { revision: 1 } });
  });

  it('copies a request before an awaiting storage operation and rejects a late older arrival', async () => {
    await loadBackground();
    const gate = deferred();
    mocks.get.mockImplementationOnce(async () => { await gate.promise; return { [ownerKey]: { clientId: 'test-document', documentStartedAt: 1000 } }; });
    const input = snapshot(2);
    const pending = send({ type: 'XFI_SESSION_WRITE', snapshot: input });
    input.observations[0]!.observation_id = 'mutated-after-send';
    gate.resolve();
    expect(await pending).toEqual({ ok: true });
    expect((mocks.records.get(key) as CollectorSessionSnapshot).observations[0]).toEqual({ observation_id: 'post-2' });
    expect(await send({ type: 'XFI_SESSION_WRITE', snapshot: snapshot(1) })).toMatchObject({ error: 'STALE_SESSION_WRITE' });
  });

  it('keeps a clear tombstone against delayed old writes, then permits a new session', async () => {
    await loadBackground();
    await send({ type: 'XFI_SESSION_WRITE', snapshot: snapshot(4) });
    await send({ type: 'XFI_SESSION_CLEAR', revision: 6, sessionId: 'session-a' });
    expect(await send({ type: 'XFI_SESSION_WRITE', snapshot: snapshot(5) })).toMatchObject({ ok: false, error: 'STALE_SESSION_WRITE' });
    expect((await send({ type: 'XFI_SESSION_READ' })).snapshot).toBeNull();
    await send({ type: 'XFI_SESSION_WRITE', snapshot: snapshot(7, 'session-b') });
    expect(await send({ type: 'XFI_SESSION_CLEAR', revision: 8, sessionId: 'session-a' })).toMatchObject({ stale: true });
    expect((await send({ type: 'XFI_SESSION_READ' })).snapshot.sessionId).toBe('session-b');
  });

  it('retains a safe export snapshot but blocks recovery after a failed write', async () => {
    await loadBackground();
    await send({ type: 'XFI_SESSION_WRITE', snapshot: snapshot(1) });
    mocks.set.mockImplementationOnce(async () => { throw new Error('quota'); });
    expect(await send({ type: 'XFI_SESSION_WRITE', snapshot: snapshot(2) })).toMatchObject({ ok: false, error: 'SESSION_STORAGE_WRITE_FAILED' });
    expect(await send({ type: 'XFI_SESSION_FAIL_CLOSED', revision: 3, sessionId: 'session-a' })).toEqual({ ok: true });
    expect(await send({ type: 'XFI_SESSION_WRITE', snapshot: snapshot(4) })).toMatchObject({ error: 'SESSION_BLOCKED' });
    expect(await send({ type: 'XFI_SESSION_READ' })).toMatchObject({ blocked: true, snapshot: { revision: 1, sessionId: 'session-a' } });
    expect(mocks.records.get(failedKey)).toEqual({ revision: 3, sessionId: 'session-a' });
    await send({ type: 'XFI_SESSION_CLEAR', revision: 5, sessionId: 'session-a' });
    await send({ type: 'XFI_SESSION_WRITE', snapshot: snapshot(6, 'session-b') });
    expect(await send({ type: 'XFI_SESSION_READ' })).toMatchObject({ snapshot: { sessionId: 'session-b' } });
  });

  it('blocks recovery when the first snapshot write fails and a marker is retained', async () => {
    await loadBackground();
    mocks.set.mockImplementationOnce(async () => { throw new Error('quota'); });
    expect(await send({ type: 'XFI_SESSION_WRITE', snapshot: snapshot(1) })).toMatchObject({ error: 'SESSION_STORAGE_WRITE_FAILED' });
    await send({ type: 'XFI_SESSION_FAIL_CLOSED', revision: 2, sessionId: 'session-a' });
    expect(await send({ type: 'XFI_SESSION_READ' })).toEqual({ snapshot: null, blocked: true });
  });

  it('recreates its event page and still rejects an old revision from stored state', async () => {
    await loadBackground();
    await send({ type: 'XFI_SESSION_WRITE', snapshot: snapshot(10, 'session-a', 'STOPPED') });
    vi.resetModules();
    await loadBackground();
    expect(await send({ type: 'XFI_SESSION_WRITE', snapshot: snapshot(9) })).toMatchObject({ error: 'STALE_SESSION_WRITE' });
    expect((await send({ type: 'XFI_SESSION_READ' })).snapshot.revision).toBe(10);
  });

  it('claims a new document owner and rejects an old higher revision even after event-page recreation', async () => {
    await loadBackground();
    await send({ type: 'XFI_SESSION_WRITE', snapshot: snapshot(10, 'new-session') });
    expect(await send({ type: 'XFI_SESSION_READ' }, 'refreshed-document', 2000)).toMatchObject({ snapshot: { revision: 10 } });
    expect(mocks.records.get(ownerKey)).toEqual({ clientId: 'refreshed-document', documentStartedAt: 2000 });
    expect(await send({ type: 'XFI_SESSION_WRITE', snapshot: snapshot(99, 'old-session') })).toMatchObject({ error: 'SESSION_OWNER_CHANGED' });
    expect((mocks.records.get(key) as CollectorSessionSnapshot).sessionId).toBe('new-session');
    vi.resetModules();
    await loadBackground();
    expect(await send({ type: 'XFI_SESSION_READ' }, 'test-document', 1000)).toMatchObject({ blocked: true, error: 'STALE_SESSION_OWNER' });
    expect(await send({ type: 'XFI_SESSION_READ' }, 'refreshed-document', 2000)).toMatchObject({ snapshot: { revision: 10 } });
    expect(mocks.records.get(ownerKey)).toEqual({ clientId: 'refreshed-document', documentStartedAt: 2000 });
    expect(await send({ type: 'XFI_SESSION_CLEAR', revision: 100, sessionId: 'old-session' })).toMatchObject({ error: 'SESSION_OWNER_CHANGED' });
    expect(await send({ type: 'XFI_SESSION_WRITE', snapshot: snapshot(11, 'new-session') }, 'refreshed-document')).toEqual({ ok: true });
    expect((mocks.records.get(key) as CollectorSessionSnapshot).revision).toBe(11);
  });

  it('does not let a delayed old READ or equal-time different client reclaim a newer document', async () => {
    await loadBackground();
    expect(await send({ type: 'XFI_SESSION_READ' }, 'new-document', 2000)).toMatchObject({ snapshot: null });
    expect(await send({ type: 'XFI_SESSION_READ' }, 'new-document', 2000)).toMatchObject({ snapshot: null });
    expect(await send({ type: 'XFI_SESSION_READ' }, 'old-document', 1000)).toMatchObject({ blocked: true, error: 'STALE_SESSION_OWNER' });
    expect(await send({ type: 'XFI_SESSION_READ' }, 'ambiguous-document', 2000)).toMatchObject({ blocked: true, error: 'STALE_SESSION_OWNER' });
    expect(mocks.records.get(ownerKey)).toEqual({ clientId: 'new-document', documentStartedAt: 2000 });
    expect(await send({ type: 'XFI_SESSION_WRITE', snapshot: snapshot(1) }, 'new-document')).toEqual({ ok: true });
    expect(await send({ type: 'XFI_SESSION_WRITE', snapshot: snapshot(2) }, 'old-document')).toMatchObject({ error: 'SESSION_OWNER_CHANGED' });
    expect(await send({ type: 'XFI_SESSION_CLEAR', revision: 3, sessionId: 'session-a' }, 'old-document')).toMatchObject({ error: 'SESSION_OWNER_CHANGED' });
  });

  it('rejects a full-sized recovery snapshot before storage writes while preserving the export ceiling', async () => {
    await loadBackground();
    expect(LIMITS.maxPacketBytes).toBeGreaterThan(LIMITS.maxRefreshRecoveryBytes);
    const huge = snapshot(1);
    huge.observations = [{ visible_text: 'x'.repeat(LIMITS.maxRefreshRecoveryBytes) }];
    expect(await send({ type: 'XFI_SESSION_WRITE', snapshot: huge })).toMatchObject({ error: 'SESSION_STORAGE_LIMIT' });
    expect(mocks.set).not.toHaveBeenCalled();
  });
});
