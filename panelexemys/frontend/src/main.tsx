import "@servicoop/frontend-foundation/tokens.css";
import "@servicoop/frontend-foundation/base.css";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { App } from "./App";

const root = document.getElementById("root");
if (!root) throw new Error("No existe el nodo #root");
createRoot(root).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
