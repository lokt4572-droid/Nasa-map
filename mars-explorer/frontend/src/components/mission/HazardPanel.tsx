import { type FormEvent, useState } from "react";

import { getLayerConfig } from "../../config/mapLayers";
import { formatLat, formatLon } from "../../config/marsProjection";
import { useRefreshers } from "../../hooks/useBackendData";
import { describeError, fieldErrors } from "../../services/api";
import { createHazard, deleteHazard, updateHazard } from "../../services/datasetService";
import { mapController } from "../../services/marsMapService";
import { useAppStore } from "../../store/useAppStore";
import type { HazardSeverity, HazardSource, HazardType, HazardVerification } from "../../types/api";

const TYPES: HazardType[] = ["CRATER", "STEEP_SLOPE", "CLIFF", "BOULDER_FIELD", "SOFT_REGOLITH", "DUNE", "DUST", "OTHER"];
const SEVERITIES: HazardSeverity[] = ["UNKNOWN", "LOW", "MEDIUM", "HIGH"];
const SOURCES: HazardSource[] = ["IMAGERY_INTERPRETATION", "FIELD_OBSERVATION", "DEM_DERIVED", "OTHER"];
const VERIF: HazardVerification[] = ["UNVERIFIED", "CONFIRMED", "REJECTED"];

const emptyForm = {
  title: "",
  hazard_type: "OTHER" as HazardType,
  severity: "UNKNOWN" as HazardSeverity,
  source: "IMAGERY_INTERPRETATION" as HazardSource,
  radius_m: "",
  description: "",
  reported_by: "",
};

export default function HazardPanel() {
  const hazards = useAppStore((s) => s.hazards);
  const point = useAppStore((s) => s.selectedPoint);
  const activeMissionId = useAppStore((s) => s.activeMissionId);
  const backendOnline = useAppStore((s) => s.backend.status === "online");
  const { refreshHazards, refreshMissions } = useRefreshers();
  const [form, setForm] = useState(emptyForm);
  const [msg, setMsg] = useState<{ ok?: string; err?: string[] }>({});

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (!point) return;
    setMsg({});
    try {
      await createHazard({
        title: form.title,
        hazard_type: form.hazard_type,
        severity: form.severity,
        source: form.source,
        radius_m: form.radius_m === "" ? null : Number(form.radius_m),
        description: form.description,
        reported_by: form.reported_by,
        reference_layer: getLayerConfig(point.layerId).layerId,
        mission: activeMissionId,
        lon_east_deg: point.lon,
        lat_deg: point.lat,
        crs: point.crs,
        latitude_convention: "AS_DECLARED_BY_SOURCE",
      });
      setForm(emptyForm);
      setMsg({ ok: "Hazard report saved (status: UNVERIFIED)" });
      await refreshHazards();
      if (activeMissionId) await refreshMissions();
    } catch (err) {
      setMsg({ err: [describeError(err), ...fieldErrors(err)] });
    }
  };

  const act = async (fn: () => Promise<unknown>) => {
    try {
      await fn();
      await refreshHazards();
    } catch (err) {
      setMsg({ err: [describeError(err)] });
    }
  };

  return (
    <div className="panel-section">
      <p className="hint">
        Hazard reports are observations, not a validated safety assessment. New reports start as UNVERIFIED.
      </p>
      <h4 className="subhead">Report hazard at selected point</h4>
      {point ? (
        <div className="mono small">
          {formatLat(point.lat)} {formatLon(point.lon)}
        </div>
      ) : (
        <div className="empty">Click the map to select the hazard location.</div>
      )}
      <form className="form" onSubmit={onSubmit}>
        <input required placeholder="Title" value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} />
        <div className="form__row">
          <select value={form.hazard_type} onChange={(e) => setForm({ ...form, hazard_type: e.target.value as HazardType })} aria-label="Hazard type">
            {TYPES.map((t) => (
              <option key={t}>{t}</option>
            ))}
          </select>
          <select value={form.severity} onChange={(e) => setForm({ ...form, severity: e.target.value as HazardSeverity })} aria-label="Severity">
            {SEVERITIES.map((t) => (
              <option key={t}>{t}</option>
            ))}
          </select>
        </div>
        <div className="form__row">
          <select value={form.source} onChange={(e) => setForm({ ...form, source: e.target.value as HazardSource })} aria-label="Source">
            {SOURCES.map((t) => (
              <option key={t}>{t}</option>
            ))}
          </select>
          <input type="number" min={0} step="any" placeholder="Radius, m" value={form.radius_m} onChange={(e) => setForm({ ...form, radius_m: e.target.value })} />
        </div>
        <textarea rows={2} placeholder="Description" value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} />
        <input placeholder="Reported by" value={form.reported_by} onChange={(e) => setForm({ ...form, reported_by: e.target.value })} />
        <button className="btn" disabled={!point || !backendOnline}>
          Save hazard report
        </button>
      </form>
      {msg.ok && <div className="ok-text">{msg.ok}</div>}
      {msg.err?.map((m, i) => (
        <div key={i} className="error-text">
          {m}
        </div>
      ))}

      <h4 className="subhead">Registered hazards ({hazards.data?.length ?? 0})</h4>
      {hazards.status === "loading" && <div className="hint">Loading…</div>}
      {hazards.error && <div className="error-text">{hazards.error}</div>}
      {hazards.data?.length === 0 && <div className="empty">No hazard reports.</div>}
      <ul className="item-list">
        {hazards.data?.map((h) => (
          <li key={h.id} className="item">
            <button className="item__main" onClick={() => mapController.centerOn(h.lon_east_deg, h.lat_deg)}>
              <span className={`sev sev--${h.severity.toLowerCase()}`}>{h.severity}</span> <strong>{h.title}</strong>
              <div className="muted small">
                {h.hazard_type} · {h.source} · {formatLat(h.lat_deg, 3)} {formatLon(h.lon_east_deg, "180", 3)}
              </div>
            </button>
            <select
              value={h.verification}
              onChange={(e) => void act(() => updateHazard(h.id, { verification: e.target.value as HazardVerification }))}
              aria-label="Verification"
            >
              {VERIF.map((v) => (
                <option key={v}>{v}</option>
              ))}
            </select>
            <button
              className="btn btn--icon"
              title="Delete"
              onClick={() => window.confirm(`Delete hazard "${h.title}"?`) && void act(() => deleteHazard(h.id))}
            >
              ×
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}
