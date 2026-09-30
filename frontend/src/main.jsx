import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import "@fontsource/golos-text/400.css";
import "@fontsource/golos-text/500.css";
import "@fontsource/golos-text/600.css";
import "@fontsource/jetbrains-mono/400.css";
import "@fontsource/jetbrains-mono/500.css";
import "@tabler/icons-webfont/dist/tabler-icons.min.css";
import "./theme.css";
import { startViewportWatch, keepFocusVisible } from "./lib/viewport";

// Следим за реальной видимой высотой экрана: без этого клавиатура на телефоне
// заслоняет поля, а нижнее меню уезжает за край.
startViewportWatch();
keepFocusVisible();

ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
