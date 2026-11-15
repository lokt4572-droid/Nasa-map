import { useState } from "react";

import Header from "./components/layout/Header";
import RightPanel from "./components/layout/RightPanel";
import Sidebar from "./components/layout/Sidebar";
import CoordinateDisplay from "./components/map/CoordinateDisplay";
import MarsMap from "./components/map/MarsMap";

import LandingPage from "./components/LandingPage";
import RoverProfile from "./components/RoverProfile";

import {
  useBackendHealth,
  useInitialData,
  usePointQuery,
} from "./hooks/useBackendData";

type Page = "landing" | "rover" | "explorer";

export default function App() {
  const [currentPage, setCurrentPage] = useState<Page>("landing");

  // Keep all backend hooks unchanged.
  useBackendHealth();
  useInitialData();
  usePointQuery();

  // Page 1: Landing Page
  if (currentPage === "landing") {
    return (
      <LandingPage
        onEnter={() => setCurrentPage("rover")}
      />
    );
  }

  // Page 2: Curiosity Rover Profile
  if (currentPage === "rover") {
    return (
      <RoverProfile
        onNext={() => setCurrentPage("explorer")}
      />
    );
  }

  // Page 3: Original Mars Explorer Map
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