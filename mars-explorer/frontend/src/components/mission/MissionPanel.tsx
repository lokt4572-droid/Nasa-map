import { type FormEvent, useState } from "react";

import { formatLat, formatLon } from "../../config/marsProjection";
import { useRefreshers } from "../../hooks/useBackendData";
import OfflinePanel from "./OfflinePanel";
import { buildMissionPackage, downloadJson } from "../../offline/missionPackage";
import { saveMissionPackage } from "../../offline/localStore";
import { describeError } from "../../services/api";
import { createMission, createWaypoint, deleteMission, deleteWaypoint, updateMission } from "../../services/datasetService";
import { mapController } from "../../services/marsMapService";
import { useAppStore } from "../../store/useAppStore";
import type { MissionStatus, WaypointKind } from "../../types/api";

const KINDS: WaypointKind[] = ["BASE", "CHECKPOINT", "LANDING_SITE", "POI"];
const STATUSES: MissionStatus[] = ["PLANNED", "ACTIVE", "COMPLETED", "ABORTED"];

export default function MissionPanel() {
  const missions = useAppStore((s) => s.missions);
  const hazards = useAppStore((s) => s.hazards.data);
  const activeMissionId = useAppStore((s) => s.activeMissionId);
  const point = useAppStore((s) => s.selectedPoint);
  const backendOnline = useAppStore((s) => s.backend.status === "online");
  const setActiveMission = useAppStore((s) => s.setActiveMission);
  const { refreshMissions } = useRefreshers();

  const [name, setName] = useState("");
  const [desc, setDesc] = useState("");
  const [wp, setWp] = useState<{ name: string; kind: WaypointKind }>({ name: "", kind: "CHECKPOINT" });
  const [msg, setMsg] = useState<{ ok?: string; err?: string }>({});

  const active = missions.data?.find((m) => m.id === activeMissionId) ?? null;

  const run = async (fn: () => Promise<unknown>, ok?: string) => {
    setMsg({});
    try {
      await fn();
      if (ok) setMsg({ ok });
      await refreshMissions();
    } catch (err) {
      setMsg({ err: describeError(err) });
    }
  };

  const onCreate = (e: FormEvent) => {
    e.preventDefault();
    void run(async () => {
      const m = await createMission({ name, description: desc });
      setActiveMission(m.id);
      setName("");
      setDesc("");
    }, "Mission created");
  };

  const onAddWaypoint = (e: FormEvent) => {
    e.preventDefault();
    if (!active || !point) return;
    void run(
      () =>
        createWaypoint({
          mission: active.id,
          name: wp.name,
          kind: wp.kind,
          lon_east_deg: point.lon,
          lat_deg: point.lat,
          crs: point.crs,
          latitude_convention: "AS_DECLARED_BY_SOURCE",
        }),
      "Waypoint saved",
    ).then(() => setWp({ ...wp, name: "" }));
  };

  const saveLocal = async () => {
    if (!active) return;
    try {
      const rec = await saveMissionPackage(buildMissionPackage(active, hazards ?? []));
      setMsg({ ok: `Local copy saved in this browser (IndexedDB) at ${new Date(rec.savedAt).toLocaleString()}` });
    } catch (err) {
      setMsg({ err: `Local save failed: ${describeError(err)}` });
    }
  };

  return (
    <div className="panel-section">
      <div className="demo-banner">
        DEMO MODE — no astronaut positioning hardware is connected. Waypoints are planning points picked on the map.
      </div>
      {!backendOnline && <div className="warn-text">Backend offline: missions cannot be loaded or saved.</div>}
      {missions.error && <div className="error-text">{missions.error}</div>}

      <h4 className="subhead">Missions</h4>
      {missions.data && missions.data.length === 0 && <div className="empty">No missions yet.</div>}
      <ul className="item-list">
        {missions.data?.map((m) => (
          <li key={m.id} className={m.id === activeMissionId ? "item item--active" : "item"}>
            <button className="item__main" onClick={() => setActiveMission(m.id === activeMissionId ? null : m.id)}>
              <strong>{m.name}</strong>
              <span className="muted">
                {" "}
                · {m.status} · {m.waypoints.length} wp · {m.hazard_count} hz
              </span>
            </button>
          </li>
        ))}
      </ul>

      {active && (
        <div className="card">
          <div className="layer-card__head">
            <strong>{active.name}</strong>
            <select
              value={active.status}
              onChange={(e) => void run(() => updateMission(active.id, { status: e.target.value as MissionStatus }))}
              aria-label="Mission status"
            >
              {STATUSES.map((s) => (
                <option key={s}>{s}</option>
              ))}
            </select>
          </div>
          {active.description && <p className="hint">{active.description}</p>}
          <h5 className="subhead">Waypoints</h5>
          {active.waypoints.length === 0 && <div className="empty">No waypoints.</div>}
          <ul className="item-list">
            {active.waypoints.map((w) => (
              <li key={w.id} className="item">
                <button className="item__main" onClick={() => mapController.centerOn(w.lon_east_deg, w.lat_deg)}>
                  <strong>{w.kind}</strong> {w.name}
                  <span className="muted mono">
                    {" "}
                    {formatLat(w.lat_deg, 3)} {formatLon(w.lon_east_deg, "180", 3)}
                  </span>
                </button>
                <button className="btn btn--icon" title="Delete waypoint" onClick={() => void run(() => deleteWaypoint(w.id))}>
                  ×
                </button>
              </li>
            ))}
          </ul>
          <form className="form form--inline" onSubmit={onAddWaypoint}>
            <input required placeholder="Waypoint name" value={wp.name} onChange={(e) => setWp({ ...wp, name: e.target.value })} />
            <select value={wp.kind} onChange={(e) => setWp({ ...wp, kind: e.target.value as WaypointKind })}>
              {KINDS.map((k) => (
                <option key={k}>{k}</option>
              ))}
            </select>
            <button className="btn btn--small" disabled={!point || !backendOnline} title={point ? "" : "Select a point on the map first"}>
              Add at selected point
            </button>
          </form>
          {!point && <div className="hint">Click the map to choose the waypoint location.</div>}
          <div className="layer-card__actions">
            <button className="btn btn--small btn--ghost" onClick={() => void saveLocal()}>
              Save local copy
            </button>
            <button
              className="btn btn--small btn--ghost"
              onClick={() => downloadJson(`mission-${active.id}-package.json`, buildMissionPackage(active, hazards ?? []))}
            >
              Export package (JSON)
            </button>
            <button
              className="btn btn--small btn--danger"
              onClick={() => {
                if (window.confirm(`Delete mission "${active.name}" and its waypoints?`)) {
                  void run(() => deleteMission(active.id)).then(() => setActiveMission(null));
                }
              }}
            >
              Delete
            </button>
          </div>
        </div>
      )}

      <OfflinePanel />

      <h4 className="subhead">New mission</h4>
      <form className="form" onSubmit={onCreate}>
        <input required placeholder="Mission name" value={name} onChange={(e) => setName(e.target.value)} />
        <textarea placeholder="Description" value={desc} onChange={(e) => setDesc(e.target.value)} rows={2} />
        <button className="btn" disabled={!backendOnline}>
          Create mission
        </button>
      </form>
      {msg.ok && <div className="ok-text">{msg.ok}</div>}
      {msg.err && <div className="error-text">{msg.err}</div>}
    </div>
  );
}
