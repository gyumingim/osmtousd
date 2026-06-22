import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// 백엔드(FastAPI :8000)로 /api 프록시
export default defineConfig({
  plugins: [react()],
  server: { proxy: { "/api": "http://localhost:8000" } },
});
