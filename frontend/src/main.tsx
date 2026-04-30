import React from "react";
import ReactDOM from "react-dom/client";
import { HashRouter } from "react-router-dom";
import { App } from "@/App";
import "@/index.css";

// HashRouter (URL fragment-based routing) is used so the app is prefix-agnostic:
// the reverse proxy can mount this SPA at any path (/pulse-check, /demo, …)
// without route resolution breaking. Pair with Vite `base: "./"` so asset
// URLs in the built HTML are relative to the document.

const rootEl = document.getElementById("root");
if (!rootEl) {
  throw new Error("#root element missing from index.html");
}

ReactDOM.createRoot(rootEl).render(
  <React.StrictMode>
    <HashRouter>
      <App />
    </HashRouter>
  </React.StrictMode>,
);
