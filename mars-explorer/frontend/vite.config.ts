/// <reference types="vitest/config" />
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { viteStaticCopy } from "vite-plugin-static-copy";

// CesiumJS needs its Workers / Assets / Widgets / ThirdParty folders served as static files.
const cesiumSource = "node_modules/cesium/Build/Cesium";
const cesiumBaseUrl = "cesiumStatic";

export default defineConfig({
  plugins: [
    react(),
    viteStaticCopy({
      // stripBase: 4 drops "node_modules/cesium/Build/Cesium" so files land at /cesiumStatic/<Folder>/...
      targets: ["Workers", "ThirdParty", "Assets", "Widgets"].map((d) => ({
        src: `${cesiumSource}/${d}`,
        dest: cesiumBaseUrl,
        rename: { stripBase: 4 },
      })),
    }),
  ],
  define: { CESIUM_BASE_URL: JSON.stringify(`/${cesiumBaseUrl}`) },
  // Bind to IPv4 explicitly: on Windows "localhost" can resolve to ::1 only, and then
  // http://127.0.0.1:5173 does not open.
  server: { host: "127.0.0.1", port: 5173, strictPort: true },
  preview: { host: "127.0.0.1", port: 5173, strictPort: true },
  build: { chunkSizeWarningLimit: 6000 }, // Cesium is a single large lazily-loaded chunk
  test: {
    environment: "jsdom",
    setupFiles: ["src/test/setup.ts"],
    include: ["src/**/*.test.ts", "src/**/*.test.tsx"],
  },
});
