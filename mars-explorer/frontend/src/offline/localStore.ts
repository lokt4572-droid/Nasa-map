/**
 * IndexedDB storage for local copies of mission packages (mission, waypoints, hazards).
 * Used so that mission records survive a backend outage on this device. Stores:
 *   - missionPackages: keyPath "missionId"
 *   - pendingHazards:  locally drafted hazard reports, autoIncrement (prepared for sync)
 *   - routes:          reserved for future locally stored routes
 */
import type { MissionPackage } from "./missionPackage";

const DB_NAME = "mars-explorer";
const DB_VERSION = 1;

export function openDb(factory: IDBFactory = indexedDB): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const req = factory.open(DB_NAME, DB_VERSION);
    req.onupgradeneeded = () => {
      const db = req.result;
      if (!db.objectStoreNames.contains("missionPackages")) db.createObjectStore("missionPackages", { keyPath: "missionId" });
      if (!db.objectStoreNames.contains("pendingHazards")) db.createObjectStore("pendingHazards", { autoIncrement: true });
      if (!db.objectStoreNames.contains("routes")) db.createObjectStore("routes", { autoIncrement: true });
    };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error ?? new Error("IndexedDB open failed"));
  });
}

function tx<T>(db: IDBDatabase, store: string, mode: IDBTransactionMode, fn: (s: IDBObjectStore) => IDBRequest<T>): Promise<T> {
  return new Promise((resolve, reject) => {
    const t = db.transaction(store, mode);
    const req = fn(t.objectStore(store));
    t.oncomplete = () => resolve(req.result);
    t.onerror = () => reject(t.error ?? req.error ?? new Error("IndexedDB transaction failed"));
    t.onabort = () => reject(t.error ?? new Error("IndexedDB transaction aborted"));
  });
}

export interface StoredMissionPackage {
  missionId: number;
  savedAt: string;
  package: MissionPackage;
}

export async function saveMissionPackage(pkg: MissionPackage, factory?: IDBFactory): Promise<StoredMissionPackage> {
  const db = await openDb(factory);
  try {
    const record: StoredMissionPackage = { missionId: pkg["mission.json"].id, savedAt: new Date().toISOString(), package: pkg };
    await tx(db, "missionPackages", "readwrite", (s) => s.put(record));
    return record;
  } finally {
    db.close();
  }
}

export async function loadMissionPackage(missionId: number, factory?: IDBFactory): Promise<StoredMissionPackage | undefined> {
  const db = await openDb(factory);
  try {
    return await tx<StoredMissionPackage | undefined>(db, "missionPackages", "readonly", (s) => s.get(missionId));
  } finally {
    db.close();
  }
}

export async function listMissionPackages(factory?: IDBFactory): Promise<StoredMissionPackage[]> {
  const db = await openDb(factory);
  try {
    return await tx<StoredMissionPackage[]>(db, "missionPackages", "readonly", (s) => s.getAll());
  } finally {
    db.close();
  }
}
