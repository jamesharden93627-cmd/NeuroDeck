import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// 开发环境将 API 和 WebSocket 透明代理到本地 FastAPI 服务。
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    strictPort: true,
    proxy: {
      "/api": "http://127.0.0.1:5188",
      "/ws": {
        target: "ws://127.0.0.1:5188",
        ws: true,
      },
    },
  },
});

