import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Development: the browser talks to Vite on :5173 and /api is proxied to FastAPI on :8000.
// Release: FastAPI serves the built files from dist/, so API paths stay relative.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    strictPort: true,
    proxy: {
      "/api": { target: "http://127.0.0.1:8000", changeOrigin: false },
    },
  },
  build: { outDir: "dist", sourcemap: false },
});
