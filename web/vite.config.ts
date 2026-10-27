import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// The browser only talks to /api; Vite forwards it to FastAPI, so there is no CORS to configure.
// API_URL is http://api:8000 inside docker compose.
const apiUrl = process.env.API_URL ?? "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: apiUrl,
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ""),
      },
    },
  },
});
