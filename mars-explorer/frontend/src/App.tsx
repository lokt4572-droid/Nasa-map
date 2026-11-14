import Header from "./components/layout/Header";
import RightPanel from "./components/layout/RightPanel";
import Sidebar from "./components/layout/Sidebar";
import CoordinateDisplay from "./components/map/CoordinateDisplay";
import MarsMap from "./components/map/MarsMap";
import { useBackendHealth, useInitialData, usePointQuery } from "./hooks/useBackendData";

export default function App() {
  useBackendHealth();
  useInitialData();
  usePointQuery();
  return (
    <div className="app">
      <Header />
      <Sidebar />
      <main className="main">
        <MarsMap />
      </main>
      <RightPanel />
      <CoordinateDisplay />
    </div>
  );
}
