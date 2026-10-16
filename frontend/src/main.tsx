import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { App } from "./App";
import "./i18n";
import "./styles/global.css";
import "./styles/redesign.css";
import "./styles/vitals.css";

const root = document.getElementById("root");

if (!root) {
  throw new Error("NeuroDeck root element was not found");
}

createRoot(root).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
