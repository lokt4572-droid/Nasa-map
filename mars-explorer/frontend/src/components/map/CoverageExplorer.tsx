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
import { type DemProduct, formatResolution, productCenter, productKey, searchDemProducts } from "../../services/datasetDiscoveryService";
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
      <DemFootprintSearch />
      <div className="cov-section-title">REGIONAL IMAGERY MOSAICS</div>
      {regions.length === 0 && <div className="hint">No regional high-resolution imagery mosaic is catalogued for this body.</div>}
      {regions.map((r) => (
        <RegionCard key={r.id} region={r} />
      ))}
    </div>
  );
}

/**
 * Elevation models (DTMs) whose footprint intersects the current map view, from the provider
 * catalogue. An imagery mosaic above does not imply a DTM: only products listed here carry heights.
 */
function DemFootprintSearch() {
  const planet = useAppStore((s) => s.planet);
  const extent = useAppStore((s) => s.view.extent);
  const products = useAppStore((s) => s.coverageProducts);
  const backendOnline = useAppStore((s) => s.backend.status === "online");
  const [state, setState] = useState<{ status: "idle" | "loading" | "done" | "error"; message?: string; truncated?: boolean; matched?: number; provider?: string }>({ status: "idle" });
  const [meta, setMeta] = useState<string | null>(null);
  const body = PLANETS[planet];
  const st = useAppStore.getState();

  const search = () => {
    if (!extent || extent.length !== 4) return;
    setState({ status: "loading" });
    searchDemProducts(planet, extent as [number, number, number, number])
      .then((r) => {
        st.setCoverageProducts(r.products);
        setState({ status: "done", truncated: r.truncated, matched: r.matched_by_provider, provider: r.provider.status });
      })
      .catch((e: unknown) => {
        st.setCoverageProducts([]);
        setState({ status: "error", message: describeError(e) });
      });
  };
  const zoomTo = (p: DemProduct) => p.bbox && mapController.zoomToBBox({ west: p.bbox[0], south: p.bbox[1], east: p.bbox[2], north: p.bbox[3] });
  const openLocal3D = (p: DemProduct) => {
    const c = productCenter(p);
    if (!c || !body.mapCrs) return;
    st.selectPoint({ lon: c.lon, lat: c.lat, crs: body.mapCrs, layerId: st.activeLayerId, pickedAt: new Date().toISOString() });
    st.setTerrainProduct(productKey(p)); // after selectPoint, which resets it
    mapController.centerOn(c.lon, c.lat);
  };

  return (
    <div className="cov-dem" data-testid="coverage-dem-search">
      <div className="cov-section-title">ELEVATION MODELS (DTM) IN THIS VIEW</div>
      <div className="layer-card__actions">
        <button className="btn btn--small" onClick={search} disabled={!backendOnline || !extent || state.status === "loading"}>
          {state.status === "loading" ? "SEARCHING…" : "SEARCH DTM FOOTPRINTS"}
        </button>
        {products.length > 0 && (
          <button className="btn btn--small btn--ghost" onClick={() => (st.setCoverageProducts([]), setState({ status: "idle" }))}>
            CLEAR
          </button>
        )}
      </div>
      {!backendOnline && <div className="hint small">Backend offline: the catalogue cannot be searched.</div>}
      {state.status === "error" && <div className="error-text small">Catalogue search failed: {state.message}</div>}
      {state.status === "done" && state.provider === "NO_CATALOGUE_FOR_BODY" && (
        <div className="hint small">No searchable DTM catalogue is connected for {body.name}. Elevation exists only where a DEM file has been imported.</div>
      )}
      {state.status === "done" && state.provider !== "NO_CATALOGUE_FOR_BODY" && (
        <div className="hint small">
          {products.length} DTM product{products.length === 1 ? "" : "s"} with a footprint in this view
          {state.truncated ? ` (showing the first results of ${state.matched}; zoom in to narrow the search)` : ""}. Source: USGS Astrogeology STAC, CC0.
          {products.length === 0 && " Only global data (or imported DEMs) covers this view."}
        </div>
      )}
      {products.map((p) => {
        const k = productKey(p);
        return (
          <div key={k} className="cov-dataset">
            <div className="cov-dataset__row">
              <span>
                <strong>{p.instrument}</strong> · {formatResolution(p.resolution_m)}
              </span>
              <span className={`badge ${p.level === "LOCAL_HIGH_RESOLUTION" ? "badge--ok" : ""}`}>DEM · {p.level === "LOCAL_HIGH_RESOLUTION" ? "LOCAL HIGH-RES" : p.level}</span>
            </div>
            <div className="small muted mono wrap">{p.product_id}</div>
            <div className="layer-card__actions">
              <button className="btn btn--small btn--ghost" onClick={() => zoomTo(p)}>
                VIEW FOOTPRINT
              </button>
              <button className="btn btn--small btn--ghost" onClick={() => openLocal3D(p)} title="Read a window of this DTM at the footprint centre and show it in 3D">
                OPEN LOCAL 3D
              </button>
              <button className="btn btn--small btn--ghost" onClick={() => setMeta(meta === k ? null : k)} aria-expanded={meta === k}>
                VIEW METADATA
              </button>
            </div>
            {meta === k && (
              <dl className="lt3d__meta cov-dataset__meta">
                <dt>Dataset</dt>
                <dd>{p.title}</dd>
                <dt>Source</dt>
                <dd>
                  {p.provider} ({p.dataset_id})
                </dd>
                <dt>Resolution</dt>
                <dd>{formatResolution(p.resolution_m)} post spacing · accuracy: {p.effective_accuracy}</dd>
                <dt>Coverage</dt>
                <dd className="mono">{p.bbox ? p.bbox.map((v) => v.toFixed(3)).join(", ") : "not stated"}</dd>
                <dt>Date</dt>
                <dd>{(p.time_range.start ?? p.time_range.datetime ?? "not stated").slice(0, 10)}</dd>
                <dt>Data</dt>
                <dd>
                  DEM: {p.product_kind ?? "yes"} · orthoimage: {p.imagery_available ? "yes" : "no"} · {p.format}
                  {p.source_imagery && <><br />Derived from: {p.source_imagery}</>}
                  {p.coverage && <><br />Coverage: {p.coverage}</>}
                </dd>
                <dt>Datum</dt>
                <dd>{p.vertical_datum}</dd>
                <dt>Quality</dt>
                <dd>
                  {p.quality_status}
                  {typeof p.quality.valid_percent === "number" ? ` (${p.quality.valid_percent.toFixed(0)}% valid cells)` : ""}
                  {p.quality.note ? ` — ${p.quality.note}` : ""}
                </dd>
                <dt>Licence</dt>
                <dd>
                  {p.license} · {p.attribution}
                </dd>
                <dt>Links</dt>
                <dd>
                  {p.source_url && (
                    <a href={p.source_url} target="_blank" rel="noreferrer">
                      catalogue record
                    </a>
                  )}
                  {p.docs_url && (
                    <>
                      {" · "}
                      <a href={p.docs_url} target="_blank" rel="noreferrer">
                        documentation
                      </a>
                    </>
                  )}
                  {p.quality.qa_metrics_url && (
                    <>
                      {" · "}
                      <a href={p.quality.qa_metrics_url} target="_blank" rel="noreferrer">
                        QA metrics
                      </a>
                    </>
                  )}
                </dd>
              </dl>
            )}
          </div>
        );
      })}
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
