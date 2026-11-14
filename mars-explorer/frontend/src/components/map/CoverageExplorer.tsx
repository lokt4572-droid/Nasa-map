import { useEffect, useState } from "react";

import { PLANETS } from "../../config/planetRegistry";
import { formatLat, formatLon } from "../../config/marsProjection";
import { describeError } from "../../services/api";
import {
  bboxAreaKm2,
  coverageRegions,
  demAvailability,
  type CoverageRegion,
  type DemAvailability,
} from "../../services/coverageCatalog";
import { mapController } from "../../services/marsMapService";
import { useAppStore } from "../../store/useAppStore";
import type { MarsMapLayer } from "../../config/mapLayers";

/**
 * "HIGH-RESOLUTION COVERAGE": every regional dataset in the catalogue, grouped by region, with its
 * outline on the map. Replaces the old Jezero-only shortcut.
 */
export default function CoverageExplorer() {
  const planet = useAppStore((s) => s.planet);
  const open = useAppStore((s) => s.coverageExplorerOpen);
  const setOpen = useAppStore((s) => s.setCoverageExplorerOpen);
  const regions = coverageRegions(planet);
  if (!open) return null;
  return (
    <div className="cov-explorer" role="dialog" aria-label="High-resolution coverage" data-testid="coverage-explorer">
      <div className="cov-explorer__head">
        <span className="cov-explorer__title">HIGH-RESOLUTION COVERAGE</span>
        <button className="btn btn--icon" onClick={() => setOpen(false)} aria-label="Close coverage explorer">
          ×
        </button>
      </div>
      <p className="hint small">
        Regional datasets in the catalogue for {PLANETS[planet].name} (outlined on the map). Outside these areas only global data
        exists. When <em>Auto high-resolution layers</em> is on, they switch on by themselves when you zoom in.
      </p>
      {regions.length === 0 && <div className="hint">No regional high-resolution dataset is catalogued for this body.</div>}
      {regions.map((r) => (
        <RegionCard key={r.id} region={r} />
      ))}
    </div>
  );
}

function RegionCard({ region }: { region: CoverageRegion }) {
  const [dem, setDem] = useState<DemAvailability>({ status: "LOADING", label: "checking registered DEMs…", datasets: [] });
  const [meta, setMeta] = useState<string | null>(null);
  const backendOnline = useAppStore((s) => s.backend.status === "online");
  const body = PLANETS[region.planet];

  useEffect(() => {
    if (!backendOnline) return setDem({ status: "ERROR", label: "backend offline: DEM availability unknown", datasets: [] });
    let alive = true;
    demAvailability(region)
      .then((d) => alive && setDem(d))
      .catch((e: unknown) => alive && setDem({ status: "ERROR", label: `DEM availability unknown: ${describeError(e)}`, datasets: [] }));
    return () => {
      alive = false;
    };
  }, [region.id, backendOnline]);

  const st = useAppStore.getState();
  const viewDataset = (l: MarsMapLayer) => mapController.zoomToBBox(l.bbox);
  const openImagery = (l: MarsMapLayer) => {
    st.setLayerVisible(l.id, true); // explicit user choice: also sets it active
    mapController.zoomToBBox(l.bbox);
  };
  const openLocal3D = () => {
    st.selectPoint({ lon: region.center.lon, lat: region.center.lat, crs: body.mapCrs!, layerId: st.activeLayerId, pickedAt: new Date().toISOString() });
    mapController.centerOn(region.center.lon, region.center.lat);
  };

  return (
    <div className="cov-region" data-testid={`coverage-region-${region.id}`}>
      <div className="cov-region__head">
        <strong>{region.name}</strong>
        <span className="muted small">{region.context}</span>
      </div>
      <div className="small muted mono">
        {formatLat(region.center.lat, 2)} {formatLon(region.center.lon, "180", 2)} · ≈{Math.round(bboxAreaKm2(region.bbox, body.radiusEquatorial)).toLocaleString()} km²
      </div>
      <div className={`small cov-region__dem cov-region__dem--${dem.status.toLowerCase()}`}>DEM: {dem.label}</div>
      {region.datasets.map((l) => (
        <div key={l.id} className="cov-dataset">
          <div className="cov-dataset__row">
            <span>
              <strong>{l.instrument}</strong> · {l.resolution}
            </span>
            <span className="badge badge--ok">IMAGERY</span>
          </div>
          <div className="layer-card__actions">
            <button className="btn btn--small btn--ghost" onClick={() => viewDataset(l)} title="Zoom to the dataset's coverage">
              VIEW DATASET
            </button>
            <button className="btn btn--small btn--ghost" onClick={() => openImagery(l)} title="Switch the layer on and zoom to it">
              OPEN IMAGERY
            </button>
            <button className="btn btn--small btn--ghost" onClick={openLocal3D} title="Open the local 3D terrain at the region centre (needs a DEM)">
              OPEN LOCAL 3D
            </button>
            <button className="btn btn--small btn--ghost" onClick={() => setMeta(meta === l.id ? null : l.id)} aria-expanded={meta === l.id}>
              VIEW METADATA
            </button>
          </div>
          {meta === l.id && (
            <dl className="lt3d__meta cov-dataset__meta">
              <dt>Product</dt>
              <dd className="mono">{l.layerId}</dd>
              <dt>Mission</dt>
              <dd>{l.mission}</dd>
              <dt>Resolution</dt>
              <dd>{l.resolution}</dd>
              <dt>Bbox</dt>
              <dd className="mono">
                {l.bbox.west.toFixed(4)}, {l.bbox.south.toFixed(4)}, {l.bbox.east.toFixed(4)}, {l.bbox.north.toFixed(4)}
              </dd>
              <dt>CRS</dt>
              <dd className="mono">{l.crs}</dd>
              <dt>Date</dt>
              <dd>{l.acquisition ?? "not stated"}</dd>
              <dt>Levels</dt>
              <dd>{l.tileMatrixLevelsVerified} tile matrix levels (verified {l.verifiedAt})</dd>
              <dt>Source</dt>
              <dd>
                <a href={l.capabilitiesUrl} target="_blank" rel="noreferrer">
                  GetCapabilities
                </a>
                {l.sourceUrl && (
                  <>
                    {" · "}
                    <a href={l.sourceUrl} target="_blank" rel="noreferrer">
                      NASA Trek
                    </a>
                  </>
                )}
              </dd>
              <dt>Note</dt>
              <dd>{l.description}</dd>
            </dl>
          )}
        </div>
      ))}
    </div>
  );
}
