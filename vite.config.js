import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// В бою приложение живёт по адресу /app/ — на / стоит сайт-витрина.
// В разработке база остаётся "/", чтобы npm run dev работал как раньше.
export default defineConfig(({ mode }) => ({
  base: mode === "production" ? "/app/" : "/",
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": "http://localhost:8000",
    },
  },
}));
