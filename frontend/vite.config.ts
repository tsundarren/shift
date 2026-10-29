import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// In development, /api is forwarded to the FastAPI server so the browser sees a single origin (no CORS setup).
export default defineConfig({
  plugins: [react()],
  server: { port: 5173, proxy: { "/api": "http://localhost:8000" } },
  test: { environment: "node", include: ["src/**/*.test.ts"] },
});
