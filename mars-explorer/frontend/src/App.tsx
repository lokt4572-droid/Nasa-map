import Header from "./components/layout/Header";
import RightPanel from "./components/layout/RightPanel";
import Sidebar from "./components/layout/Sidebar";
import CoordinateDisplay from "./components/map/CoordinateDisplay";
import MarsMap from "./components/map/MarsMap";
import { useEffect } from "react";

import EarthMap from "./components/earth/EarthMap";
import EarthPointPanel from "./components/earth/EarthPointPanel";
import Globe3D from "./components/earth/Globe3D";
import ErrorBoundary from "./components/common/ErrorBoundary";
import { geolocation } from "./services/geolocationService";
import VenusPreview from "./components/planets/VenusPreview";
import PlanetGlobe3D from "./components/planetary/PlanetGlobe3D";
import ViewModeSwitch from "./components/layout/ViewModeSwitch";
import { textureFor } from "./config/planetTextures";
import { useBackendHealth, useInitialData, usePointQuery } from "./hooks/useBackendData";
import { useAppStore } from "./store/useAppStore";

export default function App() {
  useBackendHealth();
  useInitialData();
  usePointQuery();
  const planet = useAppStore((s) => s.planet);
  const earthView = useAppStore((s) => s.earth.view);
  const bodyView = useAppStore((s) => s.bodyView);
  // Browser geolocation is Earth-only: forget the position when leaving Earth.
  useEffect(() => {
    if (planet !== "EARTH") geolocation.reset();
  }, [planet]);
  return (
    <div className="app">
      <Header />
      <Sidebar />
      <main className="main">
        <ErrorBoundary key={`${planet}-${earthView}-${bodyView}`}>
          {planet === "VENUS" ? (
            <VenusPreview />
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
