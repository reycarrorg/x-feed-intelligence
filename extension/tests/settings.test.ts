import { beforeEach, describe, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => ({ get: vi.fn(), set: vi.fn() }));

vi.mock('wxt/browser', () => ({ browser: { storage: { local: { get: mocks.get, set: mocks.set } } } }));

beforeEach(() => {
  vi.resetModules();
  vi.clearAllMocks();
  mocks.get.mockResolvedValue({});
  mocks.set.mockResolvedValue(undefined);
});

describe('saved extension settings', () => {
  it('defaults to hands-free scrolling off and the XFI download subfolder', async () => {
    const { DEFAULT_SETTINGS, getSettings } = await import('../lib/settings');
    expect(DEFAULT_SETTINGS).toEqual({ autoScrollOnStart: false, exportSubfolder: 'XFI' });
    expect(await getSettings()).toEqual(DEFAULT_SETTINGS);
  });

  it('keeps valid saved options and falls back for an unsafe folder name', async () => {
    mocks.get.mockResolvedValue({ xfi_settings_v1: { autoScrollOnStart: true, exportSubfolder: '../Desktop' } });
    const { getSettings } = await import('../lib/settings');
    expect(await getSettings()).toEqual({ autoScrollOnStart: true, exportSubfolder: 'XFI' });
  });

  it('saves valid folder settings and rejects path components', async () => {
    const { saveSettings } = await import('../lib/settings');
    await saveSettings({ autoScrollOnStart: true, exportSubfolder: 'XFI Exports' });
    expect(mocks.set).toHaveBeenCalledWith({ xfi_settings_v1: { autoScrollOnStart: true, exportSubfolder: 'XFI Exports' } });
    await expect(saveSettings({ autoScrollOnStart: false, exportSubfolder: 'folder/subfolder' })).rejects.toThrow();
  });
});
