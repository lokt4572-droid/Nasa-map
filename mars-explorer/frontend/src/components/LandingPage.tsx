import "../styles/landing.css";

type LandingPageProps = {
  onEnter: () => void;
};

export default function LandingPage({ onEnter }: LandingPageProps) {
  return (
    <div className="mars-landing">

      {/* Static Mars background */}
      <div className="mars-background" />

      {/* Dark overlay for readable text */}
      <div className="mars-overlay" />

      {/* Navigation */}
      <nav className="landing-nav">
        <a className="landing-logo" href="#">
          NOVA
        </a>

        <div className="landing-nav-links">
          <a href="#mission">MISSION</a>
          <a href="#about">ABOUT</a>
        </div>

        <div className="mission-status">
          <span className="status-light" />
          MISSION ACTIVE
        </div>
      </nav>

      {/* Main hero section */}
      <main className="landing-hero" id="mission">

        <div className="hero-text">

          <div className="hero-label">
            <span>✦</span>
            THE NEXT FRONTIER OF HUMANITY
          </div>

          <p className="hero-overline">
            WELCOME TO THE RED PLANET
          </p>

          <h1>
            EXPLORE
            <br />
            <span>MARS.</span>
          </h1>

          <p className="hero-description">
            Discover the mysteries of the Red Planet.
            Explore its terrain, analyze dangerous regions
            and plan your next interplanetary mission.
          </p>

          <div className="hero-actions">
            <button
              className="enter-button"
              onClick={onEnter}
            >
              ENTER NOVA
              <span>↗</span>
            </button>

            <a href="#about" className="learn-button">
              DISCOVER MORE ↓
            </a>
          </div>

          <div className="hero-stats">
            <div>
              <strong>225M+</strong>
              <span>KM FROM EARTH</span>
            </div>

            <div className="stats-divider" />

            <div>
              <strong>-63°C</strong>
              <span>AVG. TEMPERATURE</span>
            </div>

            <div className="stats-divider" />

            <div>
              <strong>24.6H</strong>
              <span>ONE MARTIAN DAY</span>
            </div>
          </div>

        </div>

        {/* Floating information card */}
        <div className="mission-card">
          <div className="mission-card-top">
            <span>MISSION CONTROL</span>
            <span className="mission-dot">● LIVE</span>
          </div>

          <div className="mission-card-line" />

          <p className="card-small">DESTINATION</p>
          <h2>MARS</h2>

          <p className="card-description">
            PLANETARY EXPLORATION SYSTEM
          </p>

          <div className="mission-card-line" />

          <div className="card-bottom">
            <span>SECTOR: 04-A</span>
            <span>STATUS: READY</span>
          </div>
        </div>

      </main>

      {/* Bottom information */}
      <footer className="landing-footer" id="about">
        <span>HUMANITY'S NEXT GREAT JOURNEY</span>
        <span>EST. 2026 — NOVA</span>
      </footer>

    </div>
  );
}
