import { textureFor } from "../../config/planetTextures";
import { useAppStore } from "../../store/useAppStore";

type Mode = { id: string; label: string; title: string; active: boolean; select: () => void };

/**
 * Planet view modes over the map area. Only modes the current body supports are shown
 * (no globe without a verified texture; Cesium terrain only for Earth).
 */
export default function ViewModeSwitch() {
  const planet = useAppStore((s) => s.planet);
  const bodyView = useAppStore((s) => s.bodyView);
  const earthView = useAppStore((s) => s.earth.view);
  const { setBodyView, setEarth } = useAppStore.getState();
  if (planet === "VENUS") return null;

  const modes: Mode[] = [
    {
      id: "map",
      label: "2D MAP",
      title: "Flat map with data layers",
      active: bodyView === "MAP" && (planet !== "EARTH" || earthView === "2D"),
      select: () => {
        setBodyView("MAP");
        if (planet === "EARTH") setEarth({ view: "2D" });
      },
    },
  ];
  if (textureFor(planet)) {
    modes.push({
      id: "globe",
      label: "3D GLOBE",
      title: "Whole-body globe with a global texture (Three.js)",
      active: bodyView === "GLOBE",
      select: () => setBodyView("GLOBE"),
    });
  }
  if (planet === "EARTH") {
    modes.push({
      id: "terrain",
      label: "3D TERRAIN",
      title: "Cesium globe with terrain (requires a Cesium ion token for relief)",
      active: bodyView === "MAP" && earthView === "3D",
      select: () => {
        setBodyView("MAP");
        setEarth({ view: "3D" });
      },
    });
  }
  if (modes.length < 2) return null;

  return (
    <div className="view-modes" role="tablist" aria-label="View mode">
      {modes.map((m) => (
        <button
          key={m.id}
          role="tab"
          aria-selected={m.active}
          className={`view-modes__btn ${m.active ? "view-modes__btn--active" : ""}`}
          title={m.title}
          onClick={m.select}
        >
          {m.label}
        </button>
      ))}
    </div>
  );
}
