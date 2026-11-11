import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Dev: proxy /api to the FastAPI backend. Build: dist/ is served by the
// backend itself (see backend/app/main.py), so base stays relative-simple.
export default defineConfig({
  plugins: [react()],
  server: { proxy: { "/api": "http://127.0.0.1:8077" } },
});
