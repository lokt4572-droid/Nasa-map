
import { useState } from "react";

import Header from "./components/layout/Header";
import RightPanel from "./components/layout/RightPanel";
import Sidebar from "./components/layout/Sidebar";
import CoordinateDisplay from "./components/map/CoordinateDisplay";
import MarsMap from "./components/map/MarsMap";

import LandingPage from "./components/LandingPage";

import {
  useBackendHealth,
  useInitialData,
  usePointQuery,
} from "./hooks/useBackendData";

export default function App() {
  const [showExplorer, setShowExplorer] = useState(false);

  useBackendHealth();
  useInitialData();
  usePointQuery();

  // Show the original Mars map
  // after clicking ENTER MARS EXPLORER.
  if (showExplorer) {
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

  // First show our new landing page.
  return (
    <LandingPage
      onEnter={() => setShowExplorer(true)}
    />
  );
}
