import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  base: "/static/",
  plugins: [react()],
  root: "frontend",
  server: {
    proxy: {
      "/api": "http://127.0.0.1:18787",
      "/healthz": "http://127.0.0.1:18787",
    },
  },
  build: {
    outDir: "../static",
    emptyOutDir: true,
    rollupOptions: {
      output: {
        manualChunks: {
          charts: ["recharts"],
          motion: ["framer-motion"],
          query: ["@tanstack/react-query"],
          icons: ["lucide-react"],
        },
      },
    },
    chunkSizeWarningLimit: 700,
  },
});
