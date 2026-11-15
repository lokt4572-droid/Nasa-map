/**
 * The planetary GIS workspace (/map/): maps, 3D scenes, side panels. Kept separate from the
 * site pages so their layout and styles never mix with the map's.
 */
import { useEffect } from "react";

import ErrorBoundary from "../common/ErrorBoundary";
import EarthMap from "../earth/EarthMap";
import EarthPointPanel from "../earth/EarthPointPanel";
import Globe3D from "../earth/Globe3D";
import CoordinateDisplay from "../map/CoordinateDisplay";
import MarsMap from "../map/MarsMap";
import PlanetGlobe3D from "../planetary/PlanetGlobe3D";
import PlanetScene from "../planetary/PlanetScene";
import VenusPreview from "../planets/VenusPreview";
import { textureFor } from "../../config/planetTextures";
import { geolocation } from "../../services/geolocationService";
import { cesiumBodyFor } from "../../services/planetary/cesiumSceneService";
import { useAppStore } from "../../store/useAppStore";
import Header from "./Header";
import RightPanel from "./RightPanel";
import Sidebar from "./Sidebar";
import ViewModeSwitch from "./ViewModeSwitch";

export default function Explorer() {
  const planet = useAppStore((s) => s.planet);
  const earthView = useAppStore((s) => s.earth.view);
  const bodyView = useAppStore((s) => s.bodyView);
  const backend = useAppStore((s) => s.backend.status);
  // Browser geolocation is Earth-only: forget the position when leaving Earth.
  useEffect(() => {
    if (planet !== "EARTH") geolocation.reset();
  }, [planet]);
  return (
    <div className="app">
      <Header />
      {backend !== "online" && (
        <div className="server-banner" role="status" data-testid="server-banner">
          {backend === "unknown"
            ? "Connecting to the Nova server…"
            : "The Nova server is not answering yet — a sleeping free server can take about a minute to wake up. NASA maps keep loading meanwhile; terrain, routes and missions appear once it is online."}
        </div>
      )}
      <Sidebar />
      <main className="main">
        <ErrorBoundary key={`${planet}-${earthView}-${bodyView}`}>
          {planet === "VENUS" ? (
            <VenusPreview />
          ) : bodyView === "TILES" && cesiumBodyFor(planet) ? (
            <PlanetScene key={planet} cfg={cesiumBodyFor(planet)!} />
          ) : bodyView === "GLOBE" && textureFor(planet) ? (
            <PlanetGlobe3D key={planet} planet={planet} />
          ) : planet === "EARTH" ? (
            earthView === "3D" ? <Globe3D /> : <EarthMap />
          ) : (
            <MarsMap key={planet} />
          )}
          <ViewModeSwitch />
        </ErrorBoundary>
      </main>
      {planet === "EARTH" ? <EarthPointPanel /> : <RightPanel />}
      <CoordinateDisplay />
    </div>
  );
}
