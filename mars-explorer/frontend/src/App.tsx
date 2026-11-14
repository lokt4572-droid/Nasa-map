import Header from "./components/layout/Header";
import RightPanel from "./components/layout/RightPanel";
import Sidebar from "./components/layout/Sidebar";
import CoordinateDisplay from "./components/map/CoordinateDisplay";
import MarsMap from "./components/map/MarsMap";
import EarthPending from "./components/planets/EarthPending";
import VenusPreview from "./components/planets/VenusPreview";
import { useBackendHealth, useInitialData, usePointQuery } from "./hooks/useBackendData";
import { useAppStore } from "./store/useAppStore";

export default function App() {
  useBackendHealth();
  useInitialData();
  usePointQuery();
  const planet = useAppStore((s) => s.planet);
  return (
    <div className="app">
      <Header />
      <Sidebar />
      <main className="main">
        {planet === "VENUS" ? <VenusPreview /> : planet === "EARTH" ? <EarthPending /> : <MarsMap key={planet} />}
      </main>
      <RightPanel />
      <CoordinateDisplay />
    </div>
  );
}
