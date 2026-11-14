import { useCallback, useEffect, useState } from "react";

import { ApiError, describeError } from "../services/api";
import { getCoverage, getHealth, getSlope, listDatasets, listHazards, listMissions, sampleElevation } from "../services/datasetService";
import { useAppStore } from "../store/useAppStore";

/** Poll /health/ to show the backend connection state. */
export function useBackendHealth(intervalMs = 15_000): void {
  const setBackend = useAppStore((s) => s.setBackend);
  useEffect(() => {
    let alive = true;
    const check = async () => {
      try {
        const health = await getHealth();
        if (alive) setBackend({ status: "online", health, error: null });
      } catch (err) {
        if (alive) setBackend({ status: "offline", health: null, error: describeError(err) });
      }
    };
    void check();
    const t = setInterval(check, intervalMs);
    return () => {
      alive = false;
      clearInterval(t);
    };
  }, [intervalMs, setBackend]);
}

export function useRefreshers() {
  const setMissions = useAppStore((s) => s.setMissions);
  const setHazards = useAppStore((s) => s.setHazards);
  const setDatasets = useAppStore((s) => s.setDatasets);
  const refreshMissions = useCallback(async () => {
    setMissions({ ...useAppStore.getState().missions, status: "loading" });
    try {
      setMissions({ status: "ready", data: (await listMissions()).results, error: null });
    } catch (err) {
      setMissions({ status: "error", data: useAppStore.getState().missions.data, error: describeError(err) });
    }
  }, [setMissions]);
  const refreshHazards = useCallback(async () => {
    setHazards({ ...useAppStore.getState().hazards, status: "loading" });
    try {
      setHazards({ status: "ready", data: (await listHazards()).results, error: null });
    } catch (err) {
      setHazards({ status: "error", data: useAppStore.getState().hazards.data, error: describeError(err) });
    }
  }, [setHazards]);
  const refreshDatasets = useCallback(async () => {
    setDatasets({ ...useAppStore.getState().datasets, status: "loading" });
    try {
      setDatasets({ status: "ready", data: (await listDatasets()).results, error: null });
    } catch (err) {
      setDatasets({ status: "error", data: useAppStore.getState().datasets.data, error: describeError(err) });
    }
  }, [setDatasets]);
  return { refreshMissions, refreshHazards, refreshDatasets };
}

/** Load missions/hazards/datasets once the backend is reachable. */
export function useInitialData(): void {
  const backendStatus = useAppStore((s) => s.backend.status);
  const { refreshMissions, refreshHazards, refreshDatasets } = useRefreshers();
  useEffect(() => {
    if (backendStatus !== "online") return;
    void refreshMissions();
    void refreshHazards();
    void refreshDatasets();
  }, [backendStatus, refreshMissions, refreshHazards, refreshDatasets]);
}

/**
 * When a point is selected: ask the backend which validated DEMs cover it; only then
 * request elevation and slope. Nothing is estimated client-side.
 */
export function usePointQuery(): void {
  const point = useAppStore((s) => s.selectedPoint);
  const planet = useAppStore((s) => s.planet);
  const setPointInfo = useAppStore((s) => s.setPointInfo);
  useEffect(() => {
    if (!point) return;
    const ctrl = new AbortController();
    const fail = (err: unknown) => ({
      status: "error" as const,
      data: null,
      error: describeError(err),
      errorCode: err instanceof ApiError ? err.code : null,
    });
    (async () => {
      setPointInfo({ coverage: { status: "loading", data: null, error: null } });
      let coverage;
      try {
        coverage = await getCoverage(point.lon, point.lat, ctrl.signal, planet);
        setPointInfo({ coverage: { status: "ready", data: coverage, error: null } });
      } catch (err) {
        if (!ctrl.signal.aborted) setPointInfo({ coverage: fail(err) });
        return;
      }
      if (coverage.terrain_analysis_status !== "AVAILABLE") return;
      setPointInfo({ sample: { status: "loading", data: null, error: null }, slope: { status: "loading", data: null, error: null } });
      const [s, sl] = await Promise.allSettled([
        sampleElevation(point.lon, point.lat, ctrl.signal, planet),
        getSlope(point.lon, point.lat, ctrl.signal, planet),
      ]);
      if (ctrl.signal.aborted) return;
      setPointInfo({
        sample: s.status === "fulfilled" ? { status: "ready", data: s.value, error: null } : fail(s.reason),
        slope: sl.status === "fulfilled" ? { status: "ready", data: sl.value, error: null } : fail(sl.reason),
      });
    })();
    return () => ctrl.abort();
  }, [point, planet, setPointInfo]);
}

/** Browser network state. This says nothing about offline map availability. */
export function useOnlineStatus(): boolean {
  const [online, setOnline] = useState<boolean>(typeof navigator === "undefined" ? true : navigator.onLine);
  useEffect(() => {
    const on = () => setOnline(true);
    const off = () => setOnline(false);
    window.addEventListener("online", on);
    window.addEventListener("offline", off);
    return () => {
      window.removeEventListener("online", on);
      window.removeEventListener("offline", off);
    };
  }, [setOnline]);
  return online;
}
