import { browser } from 'wxt/browser';
import { LIMITS } from '../../lib/contracts';

type Pending = { chunks: string[]; bytes: number; sealedUrl: string | null };
const pending = new Map<string, Pending>();

browser.runtime.onMessage.addListener((message: unknown, sender) => {
  if (sender.id !== browser.runtime.id || sender.tab || !message || typeof message !== 'object' || (message as { target?: string }).target !== 'offscreen') return undefined;
  const command = message as { type: string; runId?: string; index?: number; chunk?: string; url?: string };
  if (command.type === 'XFI_BLOB_BEGIN' && command.runId && !pending.has(command.runId) && pending.size < 2) {
    pending.set(command.runId, { chunks: [], bytes: 0, sealedUrl: null });
    return Promise.resolve({ ok: true });
  }
  if (command.type === 'XFI_BLOB_RELEASE_URL' && command.url) {
    for (const [id, item] of pending) if (item.sealedUrl === command.url) { URL.revokeObjectURL(command.url); pending.delete(id); return Promise.resolve({ ok: true }); }
    return Promise.resolve({ ok: false, error: 'UNKNOWN_BLOB' });
  }
  const item = command.runId ? pending.get(command.runId) : null;
  if (!item) return Promise.resolve({ ok: false, error: 'UNKNOWN_BLOB' });
  if (command.type === 'XFI_BLOB_APPEND' && !item.sealedUrl && command.index === item.chunks.length && typeof command.chunk === 'string') {
    const size = new TextEncoder().encode(command.chunk).length;
    if (item.bytes + size + 1 > LIMITS.maxPacketBytes) return Promise.resolve({ ok: false, error: 'PACKET_LIMIT' });
    item.chunks.push(command.chunk);
    item.bytes += size;
    return Promise.resolve({ ok: true });
  }
  if (command.type === 'XFI_BLOB_SEAL' && !item.sealedUrl && item.chunks.length > 0) {
    item.sealedUrl = URL.createObjectURL(new Blob([...item.chunks, '\n'], { type: 'application/json' }));
    item.chunks = [];
    return Promise.resolve({ ok: true, url: item.sealedUrl });
  }
  if (command.type === 'XFI_BLOB_RELEASE') {
    if (item.sealedUrl) URL.revokeObjectURL(item.sealedUrl);
    pending.delete(command.runId!);
    return Promise.resolve({ ok: true });
  }
  return Promise.resolve({ ok: false, error: 'INVALID_BLOB_COMMAND' });
});
