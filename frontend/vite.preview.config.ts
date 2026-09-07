// Interactive synthetic preview only. The normal build/server config is unchanged.
import { mergeConfig } from 'vitest/config'
import config from './vite.config'

export default mergeConfig(config, {
  server: {
    host: '127.0.0.1',
    port: 5144,
    strictPort: true,
    proxy: {
      '/api': 'http://127.0.0.1:8044',
      '/auth': 'http://127.0.0.1:8044',
    },
  },
})
