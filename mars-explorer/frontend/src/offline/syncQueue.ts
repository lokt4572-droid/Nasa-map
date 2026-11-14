/**
 * Offline-first record queue (IndexedDB "syncRecords").
 *
 * Every locally created/edited mission or hazard is stored with:
 *   client_id, created_at, updated_at, sync_status, version (+ server_id once known)
 * sync_status: PENDING -> SYNCING -> SYNCED | CONFLICT | FAILED
 *
 * Rules:
 * - creates send client_id: the server returns the existing record on replay (idempotent);
 * - updates send the last known server `version`: a 409 marks the record CONFLICT and
 *   stores the server copy next to the local one — the local change is NEVER deleted;
 * - network/server errors mark FAILED and the record is retried on the next sync.
 */
import { ApiError, apiRequest } from "../services/api";
import { openDb, tx } from "./localStore";

export type SyncStatus = "PENDING" | "SYNCING" | "SYNCED" | "CONFLICT" | "FAILED";
export type SyncKind = "hazard" | "mission";

export interface SyncRecord {
  client_id: string;
  kind: SyncKind;
  op: "create" | "update";
  payload: Record<string, unknown>;
  server_id: number | null;
  version: number | null; // last server version this change is based on
  sync_status: SyncStatus;
  created_at: string;
  updated_at: string;
  server_copy?: Record<string, unknown> | null;
  error?: string | null;
}

const ENDPOINT: Record<SyncKind, string> = { hazard: "/hazards/", mission: "/missions/" };

export function newClientId(): string {
  return crypto.randomUUID();
}

async function put(rec: SyncRecord, factory?: IDBFactory): Promise<void> {
  const db = await openDb(factory);
  try {
    await tx(db, "syncRecords", "readwrite", (s) => s.put(rec));
  } finally {
    db.close();
  }
}

export async function listRecords(factory?: IDBFactory): Promise<SyncRecord[]> {
  const db = await openDb(factory);
  try {
    return await tx<SyncRecord[]>(db, "syncRecords", "readonly", (s) => s.getAll());
  } finally {
    db.close();
  }
}

/** Store a create made while offline (or when the server could not be reached). */
export async function queueCreate(kind: SyncKind, payload: Record<string, unknown>, factory?: IDBFactory): Promise<SyncRecord> {
  const now = new Date().toISOString();
  const client_id = (payload.client_id as string | undefined) ?? newClientId();
  const rec: SyncRecord = {
    client_id,
    kind,
    op: "create",
    payload: { ...payload, client_id },
    server_id: null,
    version: null,
    sync_status: "PENDING",
    created_at: now,
    updated_at: now,
  };
  await put(rec, factory);
  return rec;
}

/** Store an edit of a server record, based on the server version the user saw. */
export async function queueUpdate(kind: SyncKind, serverId: number, baseVersion: number, patch: Record<string, unknown>, clientId?: string, factory?: IDBFactory): Promise<SyncRecord> {
  const now = new Date().toISOString();
  const rec: SyncRecord = {
    client_id: clientId ?? newClientId(),
    kind,
    op: "update",
    payload: patch,
    server_id: serverId,
    version: baseVersion,
    sync_status: "PENDING",
    created_at: now,
    updated_at: now,
  };
  await put(rec, factory);
  return rec;
}

type Requester = typeof apiRequest;

/** Push every PENDING/FAILED record. Returns counts per final status. */
export async function syncAll(request: Requester = apiRequest, factory?: IDBFactory): Promise<Record<SyncStatus, number>> {
  const counts: Record<SyncStatus, number> = { PENDING: 0, SYNCING: 0, SYNCED: 0, CONFLICT: 0, FAILED: 0 };
  for (const rec of await listRecords(factory)) {
    if (rec.sync_status !== "PENDING" && rec.sync_status !== "FAILED") {
      counts[rec.sync_status] += 1;
      continue;
    }
    await put({ ...rec, sync_status: "SYNCING", updated_at: new Date().toISOString() }, factory);
    let next: SyncRecord;
    try {
      if (rec.op === "create") {
        const res = await request<{ id: number; version: number }>(ENDPOINT[rec.kind], { method: "POST", body: rec.payload });
        next = { ...rec, sync_status: "SYNCED", server_id: res.id, version: res.version, error: null };
      } else {
        const res = await request<{ id: number; version: number }>(`${ENDPOINT[rec.kind]}${rec.server_id}/`, {
          method: "PATCH",
          body: { ...rec.payload, version: rec.version },
        });
        next = { ...rec, sync_status: "SYNCED", version: res.version, error: null };
      }
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        const server = (err.details as { server?: Record<string, unknown> } | undefined)?.server ?? null;
        next = { ...rec, sync_status: "CONFLICT", server_copy: server, error: err.message };
      } else {
        next = { ...rec, sync_status: "FAILED", error: err instanceof Error ? err.message : String(err) };
      }
    }
    next.updated_at = new Date().toISOString();
    await put(next, factory);
    counts[next.sync_status] += 1;
  }
  return counts;
}

/**
 * The user resolves a conflict explicitly:
 * - "keep-local": re-send the local change on top of the current server version;
 * - "keep-server": accept the server copy; the local change is kept in the record for reference.
 */
export async function resolveConflict(clientId: string, choice: "keep-local" | "keep-server", factory?: IDBFactory): Promise<SyncRecord | undefined> {
  const rec = (await listRecords(factory)).find((r) => r.client_id === clientId);
  if (!rec || rec.sync_status !== "CONFLICT") return rec;
  const serverVersion = (rec.server_copy?.version as number | undefined) ?? rec.version;
  const next: SyncRecord =
    choice === "keep-local"
      ? { ...rec, version: serverVersion, sync_status: "PENDING", error: null, updated_at: new Date().toISOString() }
      : { ...rec, sync_status: "SYNCED", error: "server version kept by user", updated_at: new Date().toISOString() };
  await put(next, factory);
  return next;
}
