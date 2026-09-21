import { browser } from 'wxt/browser';
import { LIMITS, type CollectorCommand, type CollectorResponse, type CollectorSessionSnapshot } from '../lib/contracts';
import { reconcileOwnedExports, startOwnedExport } from '../lib/export-retention';

type SaveRequest = { type: 'XFI_SAVE_EXPORT'; tabId: number };
type SaveReply = { ok: boolean; sessionId?: string; error?: string };
type OffscreenReply = { ok: boolean; url?: string; error?: string };
const ownedUrls = new Map<number, string>();
let offscreenCreating: Promise<void> | null = null;
let exportBusy = false;
const SESSION_PREFIX = 'xfi_tab_session_v1_';
const sessionKey = (tabId: number) => `${SESSION_PREFIX}${tabId}`;
const failedKey = (tabId: number) => `${SESSION_PREFIX}failed_${tabId}`;
const ownerKey = (tabId: number) => `${SESSION_PREFIX}owner_${tabId}`;
type SessionTombstone = { revision: number; cleared: true };
type SessionFailure = { revision: number; sessionId: string };
type SessionOwner = { clientId: string; documentStartedAt: number };
function sessionOwner(value: unknown): SessionOwner | null {
  const owner = value as Partial<SessionOwner> | null;
  return owner && typeof owner.clientId === 'string' && Number.isFinite(owner.documentStartedAt) && (owner.documentStartedAt || 0) > 0
    ? owner as SessionOwner : null;
}
const sessionQueues = new Map<number, Promise<unknown>>();
function inSessionOrder<T>(tabId: number, operation: () => Promise<T>): Promise<T> {
  const previous = sessionQueues.get(tabId) || Promise.resolve();
  const result = previous.catch(() => undefined).then(operation);
  const tail = result.then(() => undefined, () => undefined);
  sessionQueues.set(tabId, tail);
  void tail.then(() => { if (sessionQueues.get(tabId) === tail) sessionQueues.delete(tabId); });
  return result;
}
function isSnapshot(value: unknown): value is CollectorSessionSnapshot {
  const snapshot = value as CollectorSessionSnapshot | null;
  return !!snapshot && typeof snapshot === 'object' && !('cleared' in snapshot) &&
    Number.isSafeInteger(snapshot.revision) && snapshot.revision > 0 &&
    typeof snapshot.sessionId === 'string' && snapshot.sessionId.length > 0 &&
    Array.isArray(snapshot.observations) && Array.isArray(snapshot.events);
}
type ChromeOffscreen = { runtime: { getContexts: (query: { contextTypes: string[]; documentUrls: string[] }) => Promise<unknown[]> }; offscreen: { createDocument: (options: { url: string; reasons: string[]; justification: string }) => Promise<void> } };

async function ensureOffscreen(): Promise<void> {
  if (!offscreenCreating) {
    offscreenCreating = (async () => {
      const chromeApi = (globalThis as typeof globalThis & { chrome: ChromeOffscreen }).chrome;
      const documentUrl = browser.runtime.getURL('/offscreen.html');
      const contexts = await chromeApi.runtime.getContexts({ contextTypes: ['OFFSCREEN_DOCUMENT'], documentUrls: [documentUrl] });
      if (contexts.length === 0) await chromeApi.offscreen.createDocument({ url: 'offscreen.html', reasons: ['BLOBS'], justification: 'Hold the private local JSON blob through the Save As dialog.' });
    })().finally(() => { offscreenCreating = null; });
  }
  await offscreenCreating;
}

async function offscreen(message: Record<string, unknown>): Promise<OffscreenReply> {
  return await browser.runtime.sendMessage({ ...message, target: 'offscreen' }) as OffscreenReply;
}

async function collector(tabId: number, command: CollectorCommand): Promise<CollectorResponse> {
  return await browser.tabs.sendMessage(tabId, command) as CollectorResponse;
}

function releaseOwnedUrl(id: number): void {
  const url = ownedUrls.get(id);
  if (!url) return;
  ownedUrls.delete(id);
  if (typeof window === 'undefined') void offscreen({ type: 'XFI_BLOB_RELEASE_URL', url });
  else URL.revokeObjectURL(url);
}

async function saveFromTab(tabId: number): Promise<SaveReply> {
  let exportId: string | null = null;
  let url: string | null = null;
  let runId: string | null = null;
  let downloadStarted = false;
  try {
    const response = await collector(tabId, { type: 'XFI_EXPORT' });
    if (!response.ok || !response.export) throw new Error(response.error || 'EXPORT_FAILED');
    const { id, sessionId, chunkCount, totalBytes } = response.export;
    exportId = id;
    if (!Number.isSafeInteger(totalBytes) || totalBytes < 1 || totalBytes + 1 > LIMITS.maxPacketBytes || chunkCount < 1 || chunkCount > 128) throw new Error('EXPORT_SIZE_MISMATCH');
    const useOffscreen = typeof window === 'undefined';
    runId = crypto.randomUUID();
    if (useOffscreen) {
      await ensureOffscreen();
      const started = await offscreen({ type: 'XFI_BLOB_BEGIN', runId });
      if (!started.ok) throw new Error(started.error || 'BLOB_PREPARE_FAILED');
    }
    const parts: string[] = [];
    let receivedBytes = 0;
    for (let index = 0; index < chunkCount; index += 1) {
      const part = await collector(tabId, { type: 'XFI_EXPORT_CHUNK', exportId: id, index });
      if (!part.ok || typeof part.chunk !== 'string') throw new Error(part.error || 'EXPORT_CHUNK_FAILED');
      receivedBytes += new TextEncoder().encode(part.chunk).length;
      if (receivedBytes > totalBytes) throw new Error('EXPORT_SIZE_MISMATCH');
      if (useOffscreen) {
        const appended = await offscreen({ type: 'XFI_BLOB_APPEND', runId, index, chunk: part.chunk });
        if (!appended.ok) throw new Error(appended.error || 'BLOB_APPEND_FAILED');
      } else parts.push(part.chunk);
    }
    if (receivedBytes !== totalBytes) throw new Error('EXPORT_SIZE_MISMATCH');
    if (useOffscreen) {
      const sealed = await offscreen({ type: 'XFI_BLOB_SEAL', runId });
      if (!sealed.ok || !sealed.url) throw new Error(sealed.error || 'BLOB_SEAL_FAILED');
      url = sealed.url;
    } else {
      url = URL.createObjectURL(new Blob([...parts, '\n'], { type: 'application/json' }));
    }
    const started = await startOwnedExport(url);
    ownedUrls.set(started.id, url);
    downloadStarted = true;
    // A small local packet can complete before the download() promise resolves.
    try {
      const [item] = await browser.downloads.search({ id: started.id });
      if (item?.state === 'complete' || item?.state === 'interrupted') releaseOwnedUrl(started.id);
    } catch { /* The onChanged listener remains the other completion path. */ }
    void reconcileOwnedExports();
    return { ok: true, sessionId };
  } catch (error) {
    return { ok: false, error: error instanceof Error ? error.message : 'EXPORT_FAILED' };
  } finally {
    if (!downloadStarted && runId) {
      if (typeof window === 'undefined') void offscreen({ type: 'XFI_BLOB_RELEASE', runId });
      else if (url) URL.revokeObjectURL(url);
    }
    if (exportId) { try { await collector(tabId, { type: 'XFI_EXPORT_RELEASE', exportId }); } catch { /* Tab may have closed. */ } }
  }
}

export default defineBackground(() => {
  browser.runtime.onMessage.addListener((message: unknown, sender) => {
    if (message && typeof message === 'object' && sender.id === browser.runtime.id && sender.tab?.id != null) {
      const type = (message as { type?: string }).type;
      const tabId = sender.tab.id;
      const key = sessionKey(tabId);
      const clientId = (message as { clientId?: string }).clientId;
      if (typeof type === 'string' && type.startsWith('XFI_SESSION_') && (typeof clientId !== 'string' || !clientId || clientId.length > 128)) return Promise.resolve({ ok: false, blocked: true, error: 'INVALID_SESSION_OWNER' });
      if (type === 'XFI_SESSION_READ') {
        const acceptedClientId = clientId as string;
        const documentStartedAt = (message as { documentStartedAt?: number }).documentStartedAt;
        if (!Number.isFinite(documentStartedAt) || (documentStartedAt || 0) <= 0) return Promise.resolve({ snapshot: null, blocked: true, error: 'INVALID_DOCUMENT_START' });
        const startedAt = documentStartedAt as number;
        return inSessionOrder(tabId, async () => {
          try {
            const items = await browser.storage.session.get([key, failedKey(tabId), ownerKey(tabId)]);
            const snapshot = isSnapshot(items[key]) ? items[key] as CollectorSessionSnapshot : null;
            const failed = items[failedKey(tabId)] as SessionFailure | undefined;
            const existingOwner = sessionOwner(items[ownerKey(tabId)]);
            if (items[ownerKey(tabId)] && !existingOwner) return { snapshot, blocked: true, error: 'INVALID_SESSION_OWNER' };
            if (existingOwner && existingOwner.clientId === acceptedClientId && existingOwner.documentStartedAt !== startedAt) return { snapshot, blocked: true, error: 'INVALID_SESSION_OWNER' };
            if (existingOwner && existingOwner.clientId !== acceptedClientId) {
              // A different token is not proof of a newer document. The Window's
              // navigation time must advance; equality is ambiguous and blocked.
              if (startedAt <= existingOwner.documentStartedAt) return { snapshot, blocked: true, error: 'STALE_SESSION_OWNER' };
            }
            if (!existingOwner || existingOwner.clientId !== acceptedClientId) {
              try { await browser.storage.session.set({ [ownerKey(tabId)]: { clientId: acceptedClientId, documentStartedAt: startedAt } satisfies SessionOwner }); }
              catch { return { snapshot, blocked: true }; }
            }
            if (failed && snapshot?.sessionId === failed.sessionId) return { snapshot, blocked: true };
            if (failed && !snapshot && (!(items[key] as SessionTombstone | undefined)?.cleared || (items[key] as SessionTombstone).revision < failed.revision)) return { snapshot: null, blocked: true };
            return { snapshot };
          } catch { return { snapshot: null, blocked: true }; }
        });
      }
      if (type === 'XFI_SESSION_WRITE') {
        const snapshot = (message as { snapshot?: CollectorSessionSnapshot }).snapshot;
        if (!isSnapshot(snapshot)) return Promise.resolve({ ok: false, error: 'INVALID_SESSION_WRITE' });
        let copy: CollectorSessionSnapshot;
        try {
          const json = JSON.stringify(snapshot);
          if (new TextEncoder().encode(json).length > LIMITS.maxRefreshRecoveryBytes) return Promise.resolve({ ok: false, error: 'SESSION_STORAGE_LIMIT' });
          copy = JSON.parse(json) as CollectorSessionSnapshot;
        } catch { return Promise.resolve({ ok: false, error: 'INVALID_SESSION_WRITE' }); }
        return inSessionOrder(tabId, async () => {
          try {
            const items = await browser.storage.session.get([key, failedKey(tabId), ownerKey(tabId)]);
            if (sessionOwner(items[ownerKey(tabId)])?.clientId !== clientId) return { ok: false, error: 'SESSION_OWNER_CHANGED' };
            const prior = items[key] as CollectorSessionSnapshot | SessionTombstone | undefined;
            const failed = items[failedKey(tabId)] as SessionFailure | undefined;
            if (failed?.sessionId === copy.sessionId) return { ok: false, error: 'SESSION_BLOCKED' };
            if (prior && prior.revision >= copy.revision) return { ok: false, error: 'STALE_SESSION_WRITE' };
            await browser.storage.session.set({ [key]: copy });
            return { ok: true };
          } catch { return { ok: false, error: 'SESSION_STORAGE_WRITE_FAILED' }; }
        });
      }
      if (type === 'XFI_SESSION_FAIL_CLOSED') {
        const { revision, sessionId } = message as { revision?: number; sessionId?: string };
        if (!Number.isSafeInteger(revision) || !sessionId) return Promise.resolve({ ok: false });
        const acceptedRevision = revision as number;
        return inSessionOrder(tabId, async () => {
          try {
            const items = await browser.storage.session.get([key, failedKey(tabId), ownerKey(tabId)]);
            if (sessionOwner(items[ownerKey(tabId)])?.clientId !== clientId) return { ok: false, error: 'SESSION_OWNER_CHANGED' };
            const prior = items[key] as CollectorSessionSnapshot | SessionTombstone | undefined;
            const failed = items[failedKey(tabId)] as SessionFailure | undefined;
            if (prior && ('cleared' in prior || prior.sessionId !== sessionId) && prior.revision >= acceptedRevision) return { ok: true, stale: true };
            if (failed?.sessionId === sessionId && failed.revision >= acceptedRevision) return { ok: true, stale: true };
            await browser.storage.session.set({ [failedKey(tabId)]: { revision: acceptedRevision, sessionId } });
            return { ok: true };
          } catch { return { ok: false, error: 'SESSION_STORAGE_WRITE_FAILED' }; }
        });
      }
      if (type === 'XFI_SESSION_CLEAR') {
        const { revision, sessionId } = message as { revision?: number; sessionId?: string };
        if (!Number.isSafeInteger(revision) || !sessionId) return Promise.resolve({ ok: false });
        const acceptedRevision = revision as number;
        return inSessionOrder(tabId, async () => {
          try {
            const items = await browser.storage.session.get([key, ownerKey(tabId)]);
            if (sessionOwner(items[ownerKey(tabId)])?.clientId !== clientId) return { ok: false, error: 'SESSION_OWNER_CHANGED' };
            const prior = items[key] as CollectorSessionSnapshot | SessionTombstone | undefined;
            if (prior && !('cleared' in prior) && prior.sessionId !== sessionId) return { ok: true, stale: true };
            if (prior && prior.revision >= acceptedRevision) return { ok: true, stale: true };
            await browser.storage.session.set({ [key]: { revision: acceptedRevision, cleared: true } satisfies SessionTombstone });
            return { ok: true };
          } catch { return { ok: false, error: 'SESSION_STORAGE_WRITE_FAILED' }; }
        });
      }
    }
    if (message && typeof message === 'object' && (message as { type?: string }).type === 'XFI_PANEL_SAVE_EXPORT') {
      if (sender.id !== browser.runtime.id || sender.tab?.id == null || !sender.url?.startsWith('https://x.com/')) return undefined;
      if (exportBusy) return Promise.resolve({ ok: false, error: 'EXPORT_BUSY' });
      exportBusy = true;
      return saveFromTab(sender.tab.id).finally(() => { exportBusy = false; });
    }
    if (!message || typeof message !== 'object' || !('type' in message) || (message as { type?: string }).type !== 'XFI_SAVE_EXPORT') return undefined;
    if (sender.id !== browser.runtime.id || sender.tab || sender.url !== browser.runtime.getURL('/popup.html')) return undefined;
    const tabId = (message as SaveRequest).tabId;
    if (!Number.isSafeInteger(tabId) || tabId < 0) return Promise.resolve({ ok: false, error: 'INVALID_TAB' });
    if (exportBusy) return Promise.resolve({ ok: false, error: 'EXPORT_BUSY' });
    exportBusy = true;
    return saveFromTab(tabId).finally(() => { exportBusy = false; });
  });
  browser.downloads.onChanged.addListener((delta) => {
    if (delta.state?.current === 'complete' || delta.state?.current === 'interrupted') {
      releaseOwnedUrl(delta.id);
    }
    void reconcileOwnedExports();
  });
  browser.tabs.onRemoved?.addListener((tabId) => {
    void inSessionOrder(tabId, () => browser.storage.session.remove([sessionKey(tabId), failedKey(tabId), ownerKey(tabId)]));
  });
  void reconcileOwnedExports();
});
