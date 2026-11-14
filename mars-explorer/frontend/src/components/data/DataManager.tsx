import { type FormEvent, useCallback, useEffect, useState } from "react";

import { useRefreshers } from "../../hooks/useBackendData";
import { ApiError, describeError, fieldErrors } from "../../services/api";
import { type CatalogEntry, type ImportStep, getCatalog, registerDataset } from "../../services/datasetService";
import { useAppStore } from "../../store/useAppStore";

const PLANET_FILTERS = ["ALL PLANETS", "EARTH", "MARS", "MOON", "MERCURY", "VENUS"];
const TYPE_FILTERS = ["ALL TYPES", "IMAGERY", "DEM", "TOPOGRAPHY", "WEATHER", "GEOLOGY", "BATHYMETRY"];
const WORKFLOW = ["SELECT_FILE", "VALIDATE", "READ_METADATA", "CHECK_CRS", "CHECK_NODATA", "CHECK_UNITS", "CHECK_VERTICAL_DATUM", "CHECK_VALUES", "CONTROL_POINTS", "REGISTER_DATASET", "READY"];

function statusClass(s: string) {
  if (s === "VALID" || s === "ONLINE_SOURCE") return "status-chip--ready";
  if (s === "PARTIAL_COVERAGE" || s === "NOT_DOWNLOADED") return "status-chip--t-no-data";
  if (s === "INVALID" || s === "UNAVAILABLE") return "status-chip--error";
  return "";
}

function CatalogCard({ e }: { e: CatalogEntry }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="dataset-card">
      <div className="layer-card__head">
        <button className="item__main" onClick={() => setOpen(!open)} aria-expanded={open}>
          <strong>{e.dataset}</strong>
          <div className="muted small">
            {e.planet} · {e.data_type} · {e.resolution}
          </div>
        </button>
        <span className={`status-chip ${statusClass(e.status)}`}>{e.status}</span>
      </div>
      {open && (
        <dl className="dl small">
          <dt>Purpose</dt>
          <dd>{e.purpose}</dd>
          <dt>Source</dt>
          <dd>{e.source}</dd>
          <dt>Instrument</dt>
          <dd>{e.instrument}</dd>
          <dt>Product ID</dt>
          <dd className="mono wrap">{e.product_id}</dd>
          <dt>Spatial coverage</dt>
          <dd>{e.spatial_coverage}</dd>
          <dt>Temporal coverage</dt>
          <dd>{e.temporal_coverage}</dd>
          <dt>CRS</dt>
          <dd className="wrap">{e.crs}</dd>
          <dt>Units</dt>
          <dd>{e.units}</dd>
          <dt>Vertical datum</dt>
          <dd>{e.vertical_datum}</dd>
          <dt>Licence</dt>
          <dd>{e.license}</dd>
          <dt>Access</dt>
          <dd>{e.access === "ONLINE" ? "streamed online (nothing to download)" : "download + import_dem"}</dd>
          <dt>Documentation</dt>
          <dd>
            <a href={e.url} target="_blank" rel="noreferrer">
              official page
            </a>
          </dd>
          <dt>Facts</dt>
          <dd className={e.facts.includes("specification") ? "warn-text" : ""}>{e.facts}</dd>
          {e.local_datasets.length > 0 && (
            <>
              <dt>Local copies</dt>
              <dd>{e.local_datasets.map((d) => `${d.name} (${d.status})`).join(", ")}</dd>
            </>
          )}
        </dl>
      )}
    </div>
  );
}

export default function DataManager() {
  const current = useAppStore((s) => s.planet);
  const datasets = useAppStore((s) => s.datasets);
  const health = useAppStore((s) => s.backend.health);
  const backendStatus = useAppStore((s) => s.backend.status);
  const { refreshDatasets } = useRefreshers();
  const [planet, setPlanet] = useState<string>(current);
  const [type, setType] = useState("ALL TYPES");
  const [catalog, setCatalog] = useState<{ data: CatalogEntry[] | null; error: string | null }>({ data: null, error: null });

  const load = useCallback(() => {
    getCatalog(planet === "ALL PLANETS" ? undefined : planet, type === "ALL TYPES" ? undefined : type)
      .then((r) => setCatalog({ data: r.results, error: null }))
      .catch((err) => setCatalog({ data: null, error: describeError(err) }));
  }, [planet, type]);
  useEffect(() => {
    if (backendStatus === "online") load();
  }, [load, backendStatus]);

  const [form, setForm] = useState({ file_path: "", name: "", planet: current as string, instrument: "", source: "", vertical_datum: "", units: "" });
  const [submit, setSubmit] = useState<{ busy: boolean; msg: string | null; err: string[]; steps: ImportStep[] }>({ busy: false, msg: null, err: [], steps: [] });

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setSubmit({ busy: true, msg: null, err: [], steps: [{ step: "SELECT_FILE", status: "…", detail: form.file_path }] });
    try {
      const r = await registerDataset(form);
      setSubmit({ busy: false, msg: `Registered ${r.dataset.name} (${r.dataset.status}). ${r.warnings.join(" ")}`, err: [], steps: r.steps });
      void refreshDatasets();
      load();
    } catch (err) {
      const steps = err instanceof ApiError ? ((err.details as { steps?: ImportStep[] } | undefined)?.steps ?? []) : [];
      const errors = err instanceof ApiError ? ((err.details as { errors?: string[] } | undefined)?.errors ?? []) : [];
      setSubmit({ busy: false, msg: null, err: [describeError(err), ...errors, ...fieldErrors(err).filter((x) => !x.startsWith("errors") && !x.startsWith("steps") && !x.startsWith("warnings"))], steps });
    }
  };

  const local = (datasets.data ?? []).filter((d) => planet === "ALL PLANETS" || (d.planet ?? "MARS") === planet);

  return (
    <div className="panel-section">
      <div className="tabs" role="tablist" aria-label="Planet filter">
        {PLANET_FILTERS.map((p) => (
          <button key={p} className={`tab ${planet === p ? "tab--active" : ""}`} onClick={() => setPlanet(p)}>
            {p}
          </button>
        ))}
      </div>
      <div className="tabs" role="tablist" aria-label="Type filter">
        {TYPE_FILTERS.map((t) => (
          <button key={t} className={`tab ${type === t ? "tab--active" : ""}`} onClick={() => setType(t)}>
            {t}
          </button>
        ))}
      </div>

      <h4 className="subhead">Catalog ({catalog.data?.length ?? 0})</h4>
      {catalog.error && <div className="error-text">{catalog.error}</div>}
      {catalog.data?.length === 0 && <div className="empty">No products for this filter{type === "GEOLOGY" ? " (no geology products are integrated yet)" : ""}.</div>}
      {catalog.data?.map((e) => <CatalogCard key={e.key} e={e} />)}

      <h4 className="subhead">
        Local datasets{" "}
        <button className="btn btn--small btn--ghost" onClick={() => void refreshDatasets()} disabled={backendStatus !== "online"}>
          Refresh
        </button>
      </h4>
      <div className="hint">
        Data directory: <span className="mono wrap">{health?.data_dir.path ?? "unknown (backend offline)"}</span>
        <br />
        Raster backend:{" "}
        {health ? (health.raster_backend.available ? `${health.raster_backend.backend}, GDAL ${health.raster_backend.gdal_version}` : "NOT AVAILABLE") : "—"}
      </div>
      {datasets.error && <div className="error-text">{datasets.error}</div>}
      {local.length === 0 && <div className="empty">No local datasets for this filter.</div>}
      {local.map((d) => (
        <div key={d.id} className="dataset-card">
          <div className="layer-card__head">
            <strong>{d.name}</strong>
            <span className={`status-chip ${statusClass(d.status)}`}>{d.status}</span>
          </div>
          <div className="layer-card__meta">
            {d.planet ?? "MARS"} · {d.instrument || "instrument n/a"} · {d.resolution_meters ? `${(d.resolution_meters / 1000).toFixed(2)} km` : "resolution n/a"} ·{" "}
            {d.units || "units n/a"} · datum {d.vertical_datum}
          </div>
          <div className="mono wrap small">{d.file_path}</div>
          {d.file_size ? <div className="small muted">{(d.file_size / 1e6).toFixed(1)} MB · {d.checksum.slice(0, 23)}…</div> : null}
          {!d.file_exists && <div className="error-text">File missing on disk</div>}
          {d.validation_messages.map((m, i) => (
            <div key={i} className="warn-text small">
              {m.message}
            </div>
          ))}
        </div>
      ))}

      <h4 className="subhead">Import workflow</h4>
      <p className="hint small">
        Copy the file (and its PDS label) into the data directory first; the browser never uploads gigabytes. Files over the API size
        limit must use the CLI: <code>python manage.py import_dem</code>.
      </p>
      <ol className="workflow">
        {WORKFLOW.map((w) => {
          const st = submit.steps.find((s) => s.step === w);
          return (
            <li key={w} className={st ? `wf wf--${st.status.toLowerCase()}` : "wf"} title={st?.detail}>
              {w.replace(/_/g, " ")} {st ? `· ${st.status}` : ""}
            </li>
          );
        })}
      </ol>
      <form className="form" onSubmit={onSubmit}>
        <label>
          Path relative to data dir
          <input required placeholder="raw/mola/PRODUCT_LABEL.xml" value={form.file_path} onChange={(e) => setForm({ ...form, file_path: e.target.value })} />
        </label>
        <label>
          Dataset name (slug)
          <input required pattern="[-a-zA-Z0-9_]+" placeholder="mola-global" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
        </label>
        <label>
          Planet (the file CRS must match it)
          <select value={form.planet} onChange={(e) => setForm({ ...form, planet: e.target.value })}>
            {PLANET_FILTERS.slice(1).map((p) => (
              <option key={p}>{p}</option>
            ))}
          </select>
        </label>
        <label>
          Instrument
          <input placeholder="MGS MOLA" value={form.instrument} onChange={(e) => setForm({ ...form, instrument: e.target.value })} />
        </label>
        <label>
          Source / archive
          <input placeholder="NASA PDS Geosciences Node" value={form.source} onChange={(e) => setForm({ ...form, source: e.target.value })} />
        </label>
        <label>
          Vertical datum (if not in the label)
          <input value={form.vertical_datum} onChange={(e) => setForm({ ...form, vertical_datum: e.target.value })} />
        </label>
        <label>
          Units (only if absent in file)
          <input placeholder="m" value={form.units} onChange={(e) => setForm({ ...form, units: e.target.value })} />
        </label>
        <button className="btn" disabled={submit.busy || backendStatus !== "online"}>
          {submit.busy ? "Validating…" : "Validate & register"}
        </button>
      </form>
      {submit.msg && <div className="ok-text">{submit.msg}</div>}
      {submit.err.map((m, i) => (
        <div key={i} className="error-text">
          {m}
        </div>
      ))}
    </div>
  );
}
