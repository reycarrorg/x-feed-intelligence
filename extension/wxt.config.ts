import { defineConfig } from 'wxt';

export default defineConfig({
  manifestVersion: 3,
  manifest: ({ browser }) => ({
    name: 'X Feed Intelligence',
    short_name: 'XFI',
    version: '0.6.0',
    description: 'Capture visible X posts with manual or opt-in careful scrolling, then save them locally.',
    icons: {
      16: 'icon-16.png',
      32: 'icon-32.png',
      48: 'icon-48.png',
      128: 'icon-128.png',
    },
    optional_host_permissions: ['https://x.com/*'],
    permissions: browser === 'firefox' ? ['downloads', 'storage'] : ['downloads', 'storage', 'offscreen'],
    ...(browser === 'firefox' ? {
      browser_specific_settings: {
        gecko: {
          id: '{3bca689a-468a-4cd7-aa08-d61a8a83ed39}',
          strict_min_version: '140.0',
          // A user-triggered local JSON export moves visible social content outside the browser.
          data_collection_permissions: {
            required: ['websiteContent', 'personallyIdentifyingInfo', 'personalCommunications'],
          },
        },
      },
    } : {}),
    action: {
      default_title: 'X Feed Intelligence is inactive',
      default_popup: 'popup.html',
    },
  }),
});
