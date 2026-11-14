import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import "ol/ol.css";
import "./styles/app.css";
import App from "./App";
import { registerMarsProjections } from "./config/marsProjection";

registerMarsProjections();

const root = document.getElementById("root");
if (!root) throw new Error("#root element missing");
createRoot(root).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
