import { useState } from "react";

import { getLayerConfig } from "../../config/mapLayers";
import { useAppStore } from "../../store/useAppStore";

export default function MapLegend() {
  const [open, setOpen] = useState(true);
  const active = getLayerConfig(useAppStore((s) => s.activeLayerId));
  return (
    <div className={`map-legend ${open ? "" : "map-legend--closed"}`}>
      <button className="map-legend__toggle" onClick={() => setOpen(!open)} aria-expanded={open}>
        LEGEND {open ? "▾" : "▸"}
      </button>
      {open && (
        <div className="map-legend__body">
          <div className="legend-note">
            <strong>{active.name}</strong>
            <br />
            {active.dataKind === "COLOR_HILLSHADE"
              ? "Colour hillshade: colours are a visualization of relief, not elevation values."
              : active.dataKind === "THERMAL_IR_MOSAIC"
                ? "Thermal infrared: brightness is daytime surface temperature, not reflectance or elevation."
                : "Orthoimage: brightness is reflectance, not elevation."}
          </div>
          <ul className="legend-list">
            <li>
              <span className="sym sym--marker" /> Selected point
            </li>
            <li>
              <span className="sym sym--wp" /> Waypoint (active mission)
            </li>
            <li>
              <span className="sym sym--hz sym--hz-high" /> Hazard report — high
            </li>
            <li>
              <span className="sym sym--hz sym--hz-med" /> medium
            </li>
            <li>
              <span className="sym sym--hz sym--hz-low" /> low
            </li>
            <li>
              <span className="sym sym--hz sym--hz-unk" /> unknown severity
            </li>
          </ul>
        </div>
      )}
    </div>
  );
}
