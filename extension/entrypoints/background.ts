import { browser } from 'wxt/browser';
import { LIMITS, type CollectorCommand, type CollectorResponse } from '../lib/contracts';
import { reconcileOwnedExports, startOwnedExport } from '../lib/export-retention';

type SaveRequest = { type: 'XFI_SAVE_EXPORT'; tabId: number };
type SaveReply = { ok: boolean; sessionId?: string; error?: string };
type OffscreenReply = { ok: boolean; url?: string; error?: string };
const ownedUrls = new Map<number, string>();
let offscreenCreating: Promise<void> | null = null;
let exportBusy = false;
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
  void reconcileOwnedExports();
});
