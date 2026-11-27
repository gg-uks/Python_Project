import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

// 백엔드 연결: .env.local 에 VITE_API_BASE=/ 를 넣으면 /api 요청을 API_TARGET(기본 HAProxy 192.168.0.224)으로 넘김.
// VITE_API_BASE 가 없으면 public/mock-data.json 예시 데이터로 동작.
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  return {
    plugins: [react()],
    server: { port: 5173, proxy: { '/api': { target: env.API_TARGET || 'http://192.168.0.224', changeOrigin: true } } },
  }
})
