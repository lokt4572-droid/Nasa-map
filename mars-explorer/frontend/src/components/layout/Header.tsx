import { getLayerConfig } from "../../config/mapLayers";
import PlanetSwitcher from "./PlanetSwitcher";
import { formatLat, formatLon } from "../../config/marsProjection";
import { useOnlineStatus } from "../../hooks/useBackendData";
import { API_BASE_URL } from "../../services/api";
import { useAppStore } from "../../store/useAppStore";

export default function Header() {
  const backend = useAppStore((s) => s.backend);
  const cursor = useAppStore((s) => s.cursor);
  const activeLayerId = useAppStore((s) => s.activeLayerId);
  const activeLayer = activeLayerId ? getLayerConfig(activeLayerId) : null;
  const missions = useAppStore((s) => s.missions.data);
  const activeMissionId = useAppStore((s) => s.activeMissionId);
  const settings = useAppStore((s) => s.settings);
  const setSettings = useAppStore((s) => s.setSettings);
  const online = useOnlineStatus();
  const mission = missions?.find((m) => m.id === activeMissionId);

  const backendLabel = backend.status === "online" ? "API ONLINE" : backend.status === "offline" ? "API OFFLINE" : "API …";

  return (
    <header className="header">
      <div className="header__brand">
        <img src="/assets/mars-explorer.svg" alt="" width={22} height={22} />
        <span className="brand">MARS EXPLORER</span>
        <span className="version">v0.1 · technical preview</span>
      </div>
      <PlanetSwitcher />
      <div className="header__item">
        <span className="label">Expedition</span>
        <span>{mission ? `${mission.name}${mission.demo_mode ? " (DEMO)" : ""}` : "none selected"}</span>
      </div>
      <div className="header__item">
        <span className="label">Layer</span>
        <span>{activeLayer?.name ?? "—"}</span>
      </div>
      <div className="header__item header__cursor">
        <span className="label">Cursor</span>
        <span className="mono">{cursor ? `${formatLat(cursor.lat, 3)} ${formatLon(cursor.lon, settings.lonMode, 3)}` : "—"}</span>
      </div>
      <div className="header__spacer" />
      <div className="header__item header__item--keep" title="Browser network state. Map tiles always require the network in this version.">
        <span className={`dot ${online ? "dot--ok" : "dot--err"}`} />
        <span>{online ? "NETWORK" : "NO NETWORK"}</span>
      </div>
      <div className="header__item header__item--keep" title={backend.error ?? `Backend: ${API_BASE_URL}`}>
        <span className={`dot ${backend.status === "online" ? "dot--ok" : backend.status === "offline" ? "dot--err" : "dot--unk"}`} />
        <span>{backendLabel}</span>
      </div>
      <div className="header__item" title="No astronaut positioning hardware is connected">
        <span className="dot dot--unk" />
        <span>POSITIONING: NOT CONNECTED</span>
      </div>
      <div className="settings">
        <button
          className="btn btn--ghost btn--small"
          aria-expanded={settings.showSettings}
          onClick={() => setSettings({ showSettings: !settings.showSettings })}
        >
          ⚙ Settings
        </button>
        {settings.showSettings && (
          <div className="settings__menu" role="menu">
            <div className="label">Longitude display</div>
            <label className="check">
              <input type="radio" checked={settings.lonMode === "180"} onChange={() => setSettings({ lonMode: "180" })} />
              −180…180 (E/W)
            </label>
            <label className="check">
              <input type="radio" checked={settings.lonMode === "360"} onChange={() => setSettings({ lonMode: "360" })} />
              0…360 °E
            </label>
            <div className="hint">Stored values are always east-positive −180…180.</div>
            <div className="label">Backend</div>
            <div className="mono small wrap">{API_BASE_URL}</div>
          </div>
        )}
      </div>
    </header>
  );
}
