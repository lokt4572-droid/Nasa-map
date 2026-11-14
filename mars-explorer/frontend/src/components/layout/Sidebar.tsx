import { type SidebarSection, useAppStore } from "../../store/useAppStore";
import DataManager from "../data/DataManager";
import LayerSelector from "../map/LayerSelector";
import HazardPanel from "../mission/HazardPanel";
import MissionPanel from "../mission/MissionPanel";
import RoutePlanner from "../mission/RoutePlanner";
import DatasetInfo from "../terrain/DatasetInfo";
import { TerrainSection } from "../terrain/TerrainInfo";

const SECTIONS: { id: SidebarSection; label: string }[] = [
  { id: "layers", label: "Map Layers" },
  { id: "terrain", label: "Terrain" },
  { id: "science", label: "Scientific Data" },
  { id: "missions", label: "Missions" },
  { id: "routes", label: "Route Planner" },
  { id: "hazards", label: "Hazards" },
  { id: "data", label: "Data Manager" },
];

// Mission tools are Mars-only. Venus has no map service (no layer list).
const BY_PLANET: Record<string, SidebarSection[]> = {
  MARS: ["layers", "terrain", "science", "missions", "routes", "hazards", "data"],
  MOON: ["layers", "terrain", "science", "data"],
  MERCURY: ["layers", "terrain", "science", "data"],
  VENUS: ["data"],
  EARTH: ["data"],
};

export default function Sidebar() {
  const planet = useAppStore((s) => s.planet);
  const chosen = useAppStore((s) => s.section);
  const allowed = BY_PLANET[planet] ?? ["data"];
  // Fall back to the first section that exists for this body.
  const section: SidebarSection = allowed.includes(chosen) ? chosen : allowed[0]!;
  const setSection = useAppStore((s) => s.setSection);
  return (
    <aside className="sidebar">
      <nav className="sidebar__nav" aria-label="Sections">
        {SECTIONS.filter((s) => BY_PLANET[planet]?.includes(s.id)).map((s, i) => (
          <button
            key={s.id}
            className={`nav-btn ${section === s.id ? "nav-btn--active" : ""}`}
            onClick={() => setSection(s.id)}
            aria-current={section === s.id}
          >
            <span className="nav-btn__num">{i + 1}</span>
            {s.label}
          </button>
        ))}
      </nav>
      <div className="sidebar__body">
        <h3 className="panel-title">{SECTIONS.find((s) => s.id === section)?.label}</h3>
        {section === "layers" && <LayerSelector />}
        {section === "terrain" && <TerrainSection />}
        {section === "science" && <DatasetInfo />}
        {section === "missions" && <MissionPanel />}
        {section === "routes" && <RoutePlanner />}
        {section === "hazards" && <HazardPanel />}
        {section === "data" && <DataManager />}
      </div>
    </aside>
  );
}
