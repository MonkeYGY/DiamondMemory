import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { resolve } from 'path'

export default defineConfig({
  plugins: [vue()],
  root: resolve(__dirname, 'src/renderer'),
  test: {
    // Vite 将 root 指向 src/renderer，但测试需要覆盖整个 frontend/src（含 main 进程逻辑）
    root: resolve(__dirname),
    include: ['src/**/*.test.ts']
  },
  base: './',
  resolve: {
    alias: {
      '@': resolve(__dirname, 'src/renderer')
    }
  },
  build: {
    outDir: resolve(__dirname, 'dist/renderer'),
    emptyOutDir: true,
    sourcemap: false,
    minify: 'terser',
    terserOptions: {
      compress: {
        drop_console: true,
        drop_debugger: true
      },
      mangle: {
        toplevel: true
      }
    },
    rollupOptions: {
      input: resolve(__dirname, 'src/renderer/index.html'),
      output: {
        manualChunks: {
          vendor: ['vue', 'pinia']
        }
      }
    }
  },
  publicDir: resolve(__dirname, 'public'),
  server: {
    port: 5173,
    strictPort: true,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:15920',
        changeOrigin: true,
        secure: false,
        bypass(req) {
          if (req.url && (req.url.endsWith('.ts') || req.url.endsWith('.vue') || req.url.endsWith('.js'))) {
            return req.url;
          }
        }
      },
      '/health': {
        target: 'http://127.0.0.1:15920',
        changeOrigin: true,
        secure: false
      }
    }
  }
})
