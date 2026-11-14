/** Shown until Earth mode (next phase) is implemented. Honest status, no fake map. */
export default function EarthPending() {
  return (
    <div className="planet-screen">
      <div className="demo-banner">Earth mode is being implemented (v0.2 phase 5). Status: NOT_IMPLEMENTED.</div>
      <p className="hint">Planned: OpenStreetMap + NASA GIBS 2D map with dates, place search, geolocation, weather, terrain and a 3D globe.</p>
    </div>
  );
}
