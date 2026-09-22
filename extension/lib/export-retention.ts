import { browser } from 'wxt/browser';

const KEY = 'xfi_owned_exports_v1';
export const MAX_OWNED_EXPORTS = 10;
type Owned = { id: number; sequence: number; url: string; filename: string | null; state: 'pending' | 'complete' };
type Ledger = { nextSequence: number; items: Owned[] };

async function read(): Promise<Ledger> {
  const value = (await browser.storage.local.get(KEY))[KEY] as Ledger | undefined;
  if (!value || !Number.isSafeInteger(value.nextSequence) || !Array.isArray(value.items)) return { nextSequence: 1, items: [] };
  return value;
}

async function write(ledger: Ledger): Promise<void> { await browser.storage.local.set({ [KEY]: ledger }); }

function expectedName(sequence: number): string { return `xfi-capture-${String(sequence).padStart(4, '0')}.json`; }

function basename(path: string): string { return path.split(/[\\/]/).pop() || ''; }

async function exactItem(item: Owned): Promise<{ id: number; url: string; filename: string; state: string } | null> {
  const matches = await browser.downloads.search({ id: item.id });
  const found = matches.length === 1 ? matches[0]! : null;
  if (!found || found.id !== item.id || found.url !== item.url) return null;
  if (item.filename && found.filename !== item.filename) return null;
  return found;
}

/** Reconcile only IDs returned by our own downloads.download call. Never search by a broad filename. */
export async function reconcileOwnedExports(): Promise<{ retained: number; warning: string | null }> {
  const ledger = await read();
  let warning: string | null = null;
  for (const item of [...ledger.items]) {
    const found = await exactItem(item);
    if (!found) { warning = 'A tracked download changed or disappeared; no file was removed.'; continue; }
    if (found.state === 'interrupted') { ledger.items = ledger.items.filter((owned) => owned.id !== item.id); continue; }
    if (found.state === 'complete' && item.state === 'pending') {
      if (basename(found.filename) !== expectedName(item.sequence)) {
        ledger.items = ledger.items.filter((owned) => owned.id !== item.id);
        warning = 'A renamed export was saved, but is not managed for automatic recycling.';
        continue;
      }
      item.state = 'complete';
      item.filename = found.filename;
    }
  }
  // A new Save dialog may be cancelled. Delete nothing until an 11th owned file is complete.
  let completed = ledger.items.filter((item) => item.state === 'complete').sort((a, b) => a.sequence - b.sequence);
  while (completed.length > MAX_OWNED_EXPORTS) {
    const oldest = completed[0]!;
    const found = await exactItem(oldest);
    if (!found || found.state !== 'complete' || found.filename !== oldest.filename || basename(found.filename) !== expectedName(oldest.sequence)) {
      warning = 'Could not verify the oldest owned export; no file was removed.';
      break;
    }
    try {
      await browser.downloads.removeFile(oldest.id);
      ledger.items = ledger.items.filter((item) => item.id !== oldest.id);
      completed = completed.slice(1);
    } catch {
      warning = 'Could not recycle the oldest owned export; it remains on disk and in the ledger.';
      break;
    }
  }
  await write(ledger);
  return { retained: completed.length, warning };
}

export async function startOwnedExport(url: string): Promise<{ id: number; sequence: number }> {
  const ledger = await read();
  const sequence = ledger.nextSequence;
  const id = await browser.downloads.download({ url, filename: expectedName(sequence), saveAs: true, conflictAction: 'uniquify' });
  ledger.nextSequence += 1;
  ledger.items.push({ id, sequence, url, filename: null, state: 'pending' });
  await write(ledger);
  return { id, sequence };
}
