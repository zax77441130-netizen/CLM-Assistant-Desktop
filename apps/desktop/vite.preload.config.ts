import { defineConfig } from "vite";

export default defineConfig({
  build: {
    emptyOutDir: true,
    outDir: "dist/preload",
    lib: {
      entry: "src/preload/preload.ts",
      formats: ["cjs"],
      fileName: () => "preload.cjs"
    },
    rollupOptions: {
      external: ["electron"]
    }
  }
});
