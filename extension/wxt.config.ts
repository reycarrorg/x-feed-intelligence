import { defineConfig } from 'wxt';

export default defineConfig({
  manifestVersion: 3,
  manifest: {
    name: 'X Feed Intelligence',
    short_name: 'XFI',
    version: '0.3.0',
    description: 'Explicitly capture only visible X posts while you scroll, then export them for local analysis.',
    optional_host_permissions: ['https://x.com/*'],
    action: {
      default_title: 'X Feed Intelligence is inactive',
    },
  },
});
