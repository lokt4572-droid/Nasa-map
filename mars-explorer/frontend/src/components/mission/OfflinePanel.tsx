import { useCallback, useEffect, useState } from "react";

import { useRefreshers } from "../../hooks/useBackendData";
import { describeError } from "../../services/api";
import { useAppStore } from "../../store/useAppStore";
import { type SyncRecord, listRecords, resolveConflict, syncAll } from "../../offline/syncQueue";
import { restoreMissionPackage, summarizeRestore } from "../../offline/packageImport";
import { buildMissionZip, readMissionZip } from "../../offline/zipPackage";

function download(name: string, data: Uint8Array) {
  const url = URL.createObjectURL(new Blob([new Uint8Array(data)], { type: "application/zip" }));
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  a.click();
  URL.revokeObjectURL(url);
}

export default function OfflinePanel() {
  const missions = useAppStore((s) => s.missions.data);
  const hazards = useAppStore((s) => s.hazards.data);
  const datasets = useAppStore((s) => s.datasets.data);
  const activeMissionId = useAppStore((s) => s.activeMissionId);
  const planet = useAppStore((s) => s.planet);
  const online = useAppStore((s) => s.backend.status === "online");
  const { refreshMissions, refreshHazards } = useRefreshers();
  const [records, setRecords] = useState<SyncRecord[]>([]);
  const [msg, setMsg] = useState<{ ok?: string; err?: string[]; warn?: string[] }>({});
  const reload = useCallback(() => void listRecords().then(setRecords).catch(() => setRecords([])), []);
  useEffect(reload, [reload]);

  const sync = async () => {
    const counts = await syncAll();
    setMsg({ ok: `Sync finished: ${counts.SYNCED} synced, ${counts.CONFLICT} conflict(s), ${counts.FAILED} failed.` });
    reload();
    await Promise.all([refreshHazards(), refreshMissions()]);
  };

  const active = missions?.find((m) => m.id === activeMissionId);

  const exportZip = async () => {
    if (!active) return;
    try {
      const { zip, manifest } = await buildMissionZip({ mission: active, hazards: hazards ?? [], datasets: datasets ?? [], planet });
      download(`mission-${active.id}-package.zip`, zip);
      setMsg({ ok: `Exported ZIP (${manifest.files.length} files, SHA-256 manifest). No map tiles or DEM rasters are included.` });
    } catch (err) {
      setMsg({ err: [describeError(err)] });
    }
  };

  const importZip = async (file: File) => {
    if (file.size > 50 * 1024 * 1024) return setMsg({ err: ["Package larger than 50 MB refused (packages carry JSON, not rasters)."] });
    const res = await readMissionZip(new Uint8Array(await file.arrayBuffer()), planet);
    if (!res.ok || !res.mission) return setMsg({ err: res.errors, warn: res.warnings });
    try {
      const report = await restoreMissionPackage(res);
      const conflicts = [report.mission, ...report.hazards]
        .filter((r) => r.outcome === "KEPT_SERVER_COPY")
        .map((r) => `${"title" in r ? `Hazard "${r.title}"` : "Mission"} differs from the package (${r.differences.join(", ")}): the server copy was kept.`);
      const failed = report.hazards.filter((h) => h.outcome === "FAILED").map((h) => `Hazard "${h.title}": ${h.error}`);
      setMsg({ ok: summarizeRestore(report, res.mission.name), warn: [...res.warnings, ...conflicts], err: failed.length ? failed : undefined });
      await Promise.all([refreshMissions(), refreshHazards()]);
    } catch (err) {
      setMsg({ err: [describeError(err)], warn: res.warnings });
    }
  };

  const pending = records.filter((r) => r.sync_status !== "SYNCED");
  return (
    <div className="card">
      <strong>Offline data</strong>
      <p className="hint small">
        Local queue in this browser (IndexedDB). OFFLINE READY: NO — map tiles still need the network; mission records and hazard
        reports can be created offline and synced later.
      </p>
      <div className="kv">
        <span className="label">Local changes</span>
        <span className="mono">
          {pending.length} unsynced / {records.length} total
        </span>
      </div>
      <ul className="item-list">
        {pending.map((r) => (
          <li key={r.client_id} className="item">
            <div className="item__main">
              <span className={`status-chip ${r.sync_status === "CONFLICT" || r.sync_status === "FAILED" ? "status-chip--error" : ""}`}>{r.sync_status}</span>{" "}
              {r.kind} {String(r.payload.title ?? r.payload.name ?? r.server_id ?? "")}
              {r.error && <div className="small muted">{r.error}</div>}
            </div>
            {r.sync_status === "CONFLICT" && (
              <>
                <button className="btn btn--small btn--ghost" onClick={() => void resolveConflict(r.client_id, "keep-local").then(reload)}>
                  Keep mine
                </button>
                <button className="btn btn--small btn--ghost" onClick={() => void resolveConflict(r.client_id, "keep-server").then(reload)}>
                  Keep server
                </button>
              </>
            )}
          </li>
        ))}
      </ul>
      <div className="layer-card__actions">
        <button className="btn btn--small" disabled={!online || pending.length === 0} onClick={() => void sync()}>
          Sync now
        </button>
        <button className="btn btn--small btn--ghost" disabled={!active} onClick={() => void exportZip()} title={active ? "" : "Select a mission first"}>
          Export ZIP package
        </button>
        <label className="btn btn--small btn--ghost">
          Import ZIP…
          <input type="file" accept=".zip,application/zip" hidden onChange={(e) => e.target.files?.[0] && void importZip(e.target.files[0])} disabled={!online} />
        </label>
      </div>
      {msg.ok && <div className="ok-text">{msg.ok}</div>}
      {msg.err?.map((m, i) => (
        <div key={i} className="error-text">
          {m}
        </div>
      ))}
      {msg.warn?.map((m, i) => (
        <div key={i} className="warn-text small">
          {m}
        </div>
      ))}
    </div>
  );
}
