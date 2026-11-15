import { coverageRegions } from "../../services/coverageCatalog";
import { mapController } from "../../services/marsMapService";
import { useAppStore } from "../../store/useAppStore";

export default function MapControls() {
  const planet = useAppStore((s) => s.planet);
  const coverageOpen = useAppStore((s) => s.coverageExplorerOpen);
  const setCoverageOpen = useAppStore((s) => s.setCoverageExplorerOpen);
  const hasRegions = coverageRegions(planet).length > 0;
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
      {hasRegions && (
        <button
          className={`map-btn map-btn--text ${coverageOpen ? "map-btn--on" : ""}`}
          title="High-resolution coverage: all regional datasets in the catalogue"
          aria-pressed={coverageOpen}
          onClick={() => setCoverageOpen(!coverageOpen)}
        >
          COVERAGE
        </button>
      )}
    </div>
  );
}
