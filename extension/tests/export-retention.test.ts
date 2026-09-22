import { beforeEach, describe, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => ({
  ledger: { nextSequence: 1, items: [] as Array<{ id: number; sequence: number; url: string; filename: string | null; state: string; continuousPart?: true }> },
  downloads: new Map<number, { id: number; url: string; filename: string; state: string }>(),
  download: vi.fn(), removeFile: vi.fn(),
}));

vi.mock('wxt/browser', () => ({ browser: {
  storage: { local: {
    get: vi.fn(async () => ({ xfi_owned_exports_v1: mocks.ledger })),
    set: vi.fn(async (value: { xfi_owned_exports_v1: typeof mocks.ledger }) => { mocks.ledger = value.xfi_owned_exports_v1; }),
  } },
  downloads: {
    download: mocks.download,
    search: vi.fn(async ({ id }: { id: number }) => mocks.downloads.has(id) ? [mocks.downloads.get(id)] : []),
    removeFile: mocks.removeFile,
  },
} }));

beforeEach(() => {
  mocks.ledger = { nextSequence: 1, items: [] };
  mocks.downloads.clear();
  mocks.download.mockReset();
  mocks.removeFile.mockReset().mockResolvedValue(undefined);
});

describe('owned export retention', () => {
  it('uses a relative configured subfolder and disables the Save As prompt', async () => {
    const { startOwnedExport } = await import('../lib/export-retention');
    mocks.download.mockResolvedValueOnce(90);
    await startOwnedExport('blob:extension/manual');
    expect(mocks.download).toHaveBeenCalledWith({
      url: 'blob:extension/manual', filename: 'XFI/xfi-capture-0001.json', saveAs: false, conflictAction: 'uniquify',
    });
  });

  it('does not recycle an old file when the eleventh Save dialog is cancelled', async () => {
    const { startOwnedExport, reconcileOwnedExports } = await import('../lib/export-retention');
    for (let sequence = 1; sequence <= 10; sequence++) {
      const id = 100 + sequence;
      const url = `blob:extension/${sequence}`;
      mocks.download.mockResolvedValueOnce(id);
      await startOwnedExport(url);
      mocks.downloads.set(id, { id, url, filename: `/Documents/xfi-capture-${String(sequence).padStart(4, '0')}.json`, state: 'complete' });
    }
    await reconcileOwnedExports();
    mocks.download.mockRejectedValueOnce(new Error('USER_CANCELED'));
    await expect(startOwnedExport('blob:extension/11')).rejects.toThrow('USER_CANCELED');
    await reconcileOwnedExports();
    expect(mocks.removeFile).not.toHaveBeenCalled();
    expect(mocks.ledger.items).toHaveLength(10);
  });

  it('recycles only the verified oldest completed owned file after the eleventh completes', async () => {
    const { startOwnedExport, reconcileOwnedExports } = await import('../lib/export-retention');
    for (let sequence = 1; sequence <= 11; sequence++) {
      const id = 100 + sequence;
      const url = `blob:extension/${sequence}`;
      mocks.download.mockResolvedValueOnce(id);
      await startOwnedExport(url);
      mocks.downloads.set(id, { id, url, filename: `/Documents/xfi-capture-${String(sequence).padStart(4, '0')}.json`, state: sequence === 11 ? 'in_progress' : 'complete' });
    }
    await reconcileOwnedExports();
    expect(mocks.removeFile).not.toHaveBeenCalled();
    mocks.downloads.get(111)!.state = 'complete';
    await reconcileOwnedExports();
    expect(mocks.removeFile).toHaveBeenCalledExactlyOnceWith(101);
    expect(mocks.ledger.items).toHaveLength(10);
  });

  it('keeps the ownership record and warns if verified deletion fails', async () => {
    const { reconcileOwnedExports } = await import('../lib/export-retention');
    mocks.ledger = { nextSequence: 12, items: Array.from({ length: 11 }, (_, index) => {
      const sequence = index + 1;
      const id = 100 + sequence;
      const url = `blob:extension/${sequence}`;
      const filename = `/Documents/xfi-capture-${String(sequence).padStart(4, '0')}.json`;
      mocks.downloads.set(id, { id, url, filename, state: 'complete' });
      return { id, sequence, url, filename, state: 'complete' };
    }) };
    mocks.removeFile.mockRejectedValueOnce(new Error('denied'));
    const result = await reconcileOwnedExports();
    expect(result.warning).toContain('remains on disk');
    expect(mocks.ledger.items).toHaveLength(11);
  });

  it('retains every completed part of a continuous session beyond the manual ten-file cap', async () => {
    const { startOwnedExport, reconcileOwnedExports } = await import('../lib/export-retention');
    for (let sequence = 1; sequence <= 12; sequence++) {
      const id = 200 + sequence;
      const url = `blob:extension/continuous/${sequence}`;
      mocks.download.mockResolvedValueOnce(id);
      await startOwnedExport(url, true);
      mocks.downloads.set(id, { id, url, filename: `/Downloads/XFI/xfi-capture-${String(sequence).padStart(4, '0')}.json`, state: 'complete' });
    }
    await reconcileOwnedExports();
    expect(mocks.removeFile).not.toHaveBeenCalled();
    expect(mocks.ledger.items).toHaveLength(12);
    expect(mocks.ledger.items.every((item) => item.continuousPart === true)).toBe(true);
  });
});
