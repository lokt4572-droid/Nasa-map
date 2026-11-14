import { PLANETS, PLANET_ORDER } from "../../config/planetRegistry";
import { useAppStore } from "../../store/useAppStore";

const LABEL: Record<string, string> = { EARTH: "EARTH", MARS: "MARS", MOON: "MOON", MERCURY: "MERCURY", VENUS: "VENUS PREVIEW" };

export default function PlanetSwitcher() {
  const planet = useAppStore((s) => s.planet);
  const setPlanet = useAppStore((s) => s.setPlanet);
  return (
    <nav className="planet-switcher" aria-label="Celestial body">
      {PLANET_ORDER.map((id) => (
        <button
          key={id}
          className={`planet-btn ${planet === id ? "planet-btn--active" : ""} ${PLANETS[id].status === "EXPERIMENTAL" ? "planet-btn--exp" : ""}`}
          aria-pressed={planet === id}
          title={`${PLANETS[id].name} — ${PLANETS[id].status.replace("_", " ").toLowerCase()}`}
          onClick={() => setPlanet(id)}
        >
          {LABEL[id]}
        </button>
      ))}
    </nav>
  );
}
