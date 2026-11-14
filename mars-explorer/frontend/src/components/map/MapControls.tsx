import { JEZERO_REGION_LAYER_ID, getLayerConfig } from "../../config/mapLayers";
import { mapController } from "../../services/marsMapService";

export default function MapControls() {
  const jezero = getLayerConfig(JEZERO_REGION_LAYER_ID);
  return (
    <div className="map-controls" role="toolbar" aria-label="Map controls">
      <button className="map-btn" title="Zoom in" aria-label="Zoom in" onClick={() => mapController.zoomBy(1)}>
        +
      </button>
      <button className="map-btn" title="Zoom out" aria-label="Zoom out" onClick={() => mapController.zoomBy(-1)}>
        −
      </button>
      <div className="map-controls__sep" />
      <button className="map-btn map-btn--text" title="Show the whole planet" onClick={() => mapController.zoomToGlobal()}>
        GLOBAL
      </button>
      <button
        className="map-btn map-btn--text"
        title={`Zoom to Jezero region (extent of ${jezero.name} from GetCapabilities)`}
        onClick={() => mapController.zoomToBBox(jezero.bbox)}
      >
        JEZERO
      </button>
    </div>
  );
}
