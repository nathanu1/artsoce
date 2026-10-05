import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// The build lands inside the Python package so `ga play` can serve it without Node.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  build: {
    outDir: "../src/generative_agents/game/web",
    emptyOutDir: true,
    chunkSizeWarningLimit: 1600,
  },
  server: {
    proxy: { "/api": "http://127.0.0.1:8080", "/research": "http://127.0.0.1:8080" },
  },
});
