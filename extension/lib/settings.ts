import { browser } from 'wxt/browser';

const KEY = 'xfi_settings_v1';
export interface XfiSettings {
  autoScrollOnStart: boolean;
  exportSubfolder: string;
}

export const DEFAULT_SETTINGS: XfiSettings = Object.freeze({
  autoScrollOnStart: false,
  exportSubfolder: 'XFI',
});

export function validExportSubfolder(value: string): boolean {
  return /^[A-Za-z0-9][A-Za-z0-9 _-]{0,39}$/.test(value) && value.trim() === value;
}

export async function getSettings(): Promise<XfiSettings> {
  const raw = (await browser.storage.local.get(KEY))[KEY] as Partial<XfiSettings> | undefined;
  return {
    autoScrollOnStart: raw?.autoScrollOnStart === true,
    exportSubfolder: typeof raw?.exportSubfolder === 'string' && validExportSubfolder(raw.exportSubfolder)
      ? raw.exportSubfolder : DEFAULT_SETTINGS.exportSubfolder,
  };
}

export async function saveSettings(settings: XfiSettings): Promise<void> {
  if (!validExportSubfolder(settings.exportSubfolder)) throw new Error('Use one folder name (letters, numbers, spaces, _ or -; at most 40 characters).');
  await browser.storage.local.set({ [KEY]: settings });
}
