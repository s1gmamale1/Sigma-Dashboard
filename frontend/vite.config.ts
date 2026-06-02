/// <reference types="vitest/config" />
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  build: {
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (
            id.includes("node_modules/react") ||
            id.includes("node_modules/react-dom") ||
            id.includes("node_modules/@tanstack/react-query")
          ) {
            return "react";
          }
          return undefined;
        }
      }
    }
  },
  server: {
    port: 5173,
    proxy: {
      "/api": "http://127.0.0.1:8000"
    }
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    css: true
  }
});
