import { useCallback, useEffect, useState } from "react";

import { useRefreshers } from "../../hooks/useBackendData";
import { apiRequest, describeError } from "../../services/api";
import { useAppStore } from "../../store/useAppStore";
import type { Hazard, Mission } from "../../types/api";
import { type SyncRecord, listRecords, resolveConflict, syncAll } from "../../offline/syncQueue";
import { buildMissionZip, readMissionZip } from "../../offline/zipPackage";

/** Deterministic UUID-shaped id from text (so re-importing a package does not duplicate hazards). */
async function stableUuid(text: string): Promise<string> {
  const h = [...new Uint8Array(await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text)))].map((b) => b.toString(16).padStart(2, "0")).join("");
  return `${h.slice(0, 8)}-${h.slice(8, 12)}-5${h.slice(13, 16)}-a${h.slice(17, 20)}-${h.slice(20, 32)}`;
}

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
      const { zip, manifest } = await buildMissionZip({ mission: active, hazards: hazards ?? [], datasets: datasets ?? [] });
      download(`mission-${active.id}-package.zip`, zip);
      setMsg({ ok: `Exported ZIP (${manifest.files.length} files, SHA-256 manifest). No map tiles or DEM rasters are included.` });
    } catch (err) {
      setMsg({ err: [describeError(err)] });
    }
  };

  const importZip = async (file: File) => {
    if (file.size > 50 * 1024 * 1024) return setMsg({ err: ["Package larger than 50 MB refused (packages carry JSON, not rasters)."] });
    const res = await readMissionZip(new Uint8Array(await file.arrayBuffer()), "MARS");
    if (!res.ok || !res.mission) return setMsg({ err: res.errors, warn: res.warnings });
    try {
      const m = res.mission;
      const created = await apiRequest<Mission>("/missions/", { method: "POST", body: { name: m.name, description: m.description, status: m.status, client_id: res.manifest!.mission_client_id } });
      for (const h of res.hazards) {
        const body: Partial<Hazard> & { client_id: string } = {
          ...h,
          mission: created.id,
          client_id: (h as Hazard & { client_id?: string }).client_id ?? (await stableUuid(`${res.manifest!.mission_client_id}:${h.id}`)),
        };
        delete (body as Record<string, unknown>).id;
        await apiRequest("/hazards/", { method: "POST", body });
      }
      setMsg({ ok: `Imported "${m.name}" with ${res.hazards.length} hazard(s). Re-importing the same package will not duplicate records.`, warn: res.warnings });
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
