import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    // 把 /api/* 轉給 Flask 後端，前端程式碼一律打相對路徑 /api，
    // 這樣本機開發跟之後部署到 CloudFront 都不用改 base url。
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:3001',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ''),
      },
    },
  },
});
