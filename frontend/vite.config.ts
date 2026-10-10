import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// `npm run build` lands inside the Python package so `ga play` can serve it without Node.
// `npm run build:demo` makes a static page that plays a recording (`ga export-demo`), with
// relative asset paths so it can be hosted anywhere, even without a server path of its own.
export default defineConfig(({ mode }) => {
  const demo = mode === "demo";
  return {
    base: demo ? "./" : "/",
    define: { "import.meta.env.VITE_DEMO": JSON.stringify(demo ? "1" : "") },
    plugins: [react(), tailwindcss()],
    build: {
      outDir: demo ? "dist-demo" : "../src/generative_agents/game/web",
      emptyOutDir: true,
      chunkSizeWarningLimit: 1600,
      rollupOptions: demo ? { input: "demo.html" } : undefined,
    },
    server: {
      proxy: { "/api": "http://127.0.0.1:8080", "/research": "http://127.0.0.1:8080" },
    },
  };
});
