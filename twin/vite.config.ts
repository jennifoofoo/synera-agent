import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Dev: the Python API (`uv run python -m web`) listens on 127.0.0.1:8765; everything under /api is proxied there.
// The server checks Origin/Host on /api/speak and /api/level4/*, so the proxy presents itself as the same origin.
const API = process.env.TWIN_API ?? "http://127.0.0.1:8765";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5180,
    host: true,
    proxy: {
      "/api": {
        target: API,
        changeOrigin: true,
        configure(proxy) {
          proxy.on("proxyReq", (req) => req.setHeader("Origin", API));
        },
      },
    },
  },
  build: { outDir: "dist", sourcemap: false, chunkSizeWarningLimit: 1500 },
});
