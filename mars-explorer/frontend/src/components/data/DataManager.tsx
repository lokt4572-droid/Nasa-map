import { type FormEvent, useState } from "react";

import { layersForPlanet } from "../../config/mapLayers";
import { useRefreshers } from "../../hooks/useBackendData";
import { describeError, fieldErrors } from "../../services/api";
import { registerDataset } from "../../services/datasetService";
import { useAppStore } from "../../store/useAppStore";

export default function DataManager() {
  const planet = useAppStore((s) => s.planet);
  const planetLayers = layersForPlanet(planet);
  const layers = useAppStore((s) => s.layers);
  const datasets = useAppStore((s) => s.datasets);
  const health = useAppStore((s) => s.backend.health);
  const backendStatus = useAppStore((s) => s.backend.status);
  const pointInfo = useAppStore((s) => s.pointInfo.coverage.data);
  const { refreshDatasets } = useRefreshers();

  const [form, setForm] = useState({ file_path: "", name: "", instrument: "", source: "", vertical_datum: "", units: "" });
  const [submit, setSubmit] = useState<{ busy: boolean; msg: string | null; err: string[] }>({ busy: false, msg: null, err: [] });

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setSubmit({ busy: true, msg: null, err: [] });
    try {
      const r = await registerDataset(form);
      setSubmit({ busy: false, msg: `Registered ${r.dataset.name} (${r.dataset.status}). ${r.warnings.join(" ")}`, err: [] });
      void refreshDatasets();
    } catch (err) {
      const details = fieldErrors(err);
      setSubmit({ busy: false, msg: null, err: [describeError(err), ...details] });
    }
  };

  const coveringIds = new Set(pointInfo?.datasets.map((d) => d.id) ?? []);

  return (
    <div className="panel-section">
      <h4 className="subhead">Online map layers (NASA Trek WMTS)</h4>
      <table className="table">
        <thead>
          <tr>
            <th>Layer</th>
            <th>Res.</th>
            <th>State</th>
          </tr>
        </thead>
        <tbody>
          {planetLayers.map((l) => (
            <tr key={l.id}>
              <td>{l.name}</td>
              <td className="mono">{l.resolution}</td>
              <td>
                <span className={`status-chip status-chip--${layers[l.id]?.status}`}>{layers[l.id]?.status}</span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      <h4 className="subhead">
        Local DEMs (backend){" "}
        <button className="btn btn--small btn--ghost" onClick={() => void refreshDatasets()} disabled={backendStatus !== "online"}>
          Refresh
        </button>
      </h4>
      <div className="hint">
        Data directory: <span className="mono wrap">{health?.data_dir.path ?? "unknown (backend offline)"}</span>
        {health && !health.data_dir.exists && <span className="warn-text"> — directory does not exist</span>}
        <br />
        Raster backend:{" "}
        {health ? (health.raster_backend.available ? `${health.raster_backend.backend}, GDAL ${health.raster_backend.gdal_version}` : "NOT AVAILABLE") : "—"}
      </div>
      {datasets.status === "loading" && <div className="hint">Loading…</div>}
      {datasets.error && <div className="error-text">{datasets.error}</div>}
      {datasets.data && datasets.data.length === 0 && (
        <div className="empty">
          No DEM registered. Download a DEM (see data/mars/README.md) and import it with
          <code> python manage.py import_dem</code>.
        </div>
      )}
      {datasets.data?.map((d) => (
        <div key={d.id} className="dataset-card">
          <div className="layer-card__head">
            <strong>{d.name}</strong>
            <span className={`status-chip status-chip--ds-${d.status.toLowerCase()}`}>{d.status}</span>
          </div>
          <div className="layer-card__meta">
            {d.instrument || "instrument n/a"} · {d.resolution_meters ? `${d.resolution_meters.toFixed(1)} m` : "resolution n/a"} ·{" "}
            {d.units || "units n/a"} · {d.latitude_convention}
          </div>
          <div className="mono wrap small">{d.file_path}</div>
          {!d.file_exists && <div className="error-text">File missing on disk</div>}
          {coveringIds.has(d.id) && <div className="ok-text">Covers the selected point</div>}
          {d.validation_messages.map((m, i) => (
            <div key={i} className="warn-text small">
              {m.message}
            </div>
          ))}
        </div>
      ))}

      <h4 className="subhead">Register a local DEM file</h4>
      <p className="hint">
        The file must already be inside the data directory (copy it to <code>data/mars/raw/…</code>). Large files: prefer the CLI
        importer. Browser upload is intentionally not supported.
      </p>
      <form className="form" onSubmit={onSubmit}>
        <label>
          Path relative to data dir
          <input required placeholder="raw/mola/PRODUCT_LABEL.xml" value={form.file_path} onChange={(e) => setForm({ ...form, file_path: e.target.value })} />
        </label>
        <label>
          Dataset name (slug)
          <input required pattern="[-a-zA-Z0-9_]+" placeholder="mola-megdr-global" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
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
          Vertical datum (from the label)
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
