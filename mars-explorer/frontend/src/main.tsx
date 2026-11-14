import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import "ol/ol.css";
import "./styles/app.css";
import App from "./App";
import { registerPlanetProjections } from "./config/planetProjections";

registerPlanetProjections();

const root = document.getElementById("root");
if (!root) throw new Error("#root element missing");
createRoot(root).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
