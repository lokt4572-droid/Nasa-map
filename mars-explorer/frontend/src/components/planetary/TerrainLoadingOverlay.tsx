/** Loading / status overlay for 3D scenes. Never shows a success state on its own. */
export default function TerrainLoadingOverlay({ title, detail, tone = "info" }: { title: string; detail?: string | null; tone?: "info" | "warn" | "error" }) {
  return (
    <div className={`scene-overlay scene-overlay--${tone}`} role={tone === "error" ? "alert" : "status"}>
      {tone === "info" && <span className="map-diag__spinner" aria-hidden="true" />}
      <div>
        <div className="scene-overlay__title">{title}</div>
        {detail && <div className="scene-overlay__detail">{detail}</div>}
      </div>
    </div>
  );
}
