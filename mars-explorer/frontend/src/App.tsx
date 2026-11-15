import LandingPage from "./components/LandingPage";
import NotFound from "./components/NotFound";
import RoverProfile from "./components/RoverProfile";
import Explorer from "./components/layout/Explorer";
import { useBackendHealth, useInitialData, usePointQuery } from "./hooks/useBackendData";
import { navigate, usePage } from "./routes";

/**
 * Site pages by URL (see routes.ts): / landing -> /rover/ Curiosity profile -> /map/ workspace.
 * The landing and rover pages are used exactly as designed; only their buttons are wired to URLs.
 */
export default function App() {
  // Keep all backend hooks unchanged (they also preload data for the map).
  useBackendHealth();
  useInitialData();
  usePointQuery();
  const page = usePage();

  // Page 1: Landing Page
  if (page === "home") return <LandingPage onEnter={() => navigate("rover")} />;
  // Page 2: Curiosity Rover Profile
  if (page === "rover") return <RoverProfile onNext={() => navigate("map")} />;
  if (page === "notfound") return <NotFound />;
  // Page 3: Mars Explorer map workspace
  return <Explorer />;
}
