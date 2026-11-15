import { PLANETS } from "../../config/planetRegistry";

/**
 * Venus is a scientific preview only. No NASA Trek map service exists for Venus
 * (checked 2026-11-14), so no map is drawn rather than a misleading one.
 */
export default function VenusPreview() {
  const v = PLANETS.VENUS;
  return (
    <div className="planet-screen">
      <div className="demo-banner">
        EXPERIMENTAL — Venus preview. Low detail: Magellan GTDR topography is ≈ 5 × 5 km per pixel. No interactive map is
        available because no NASA Trek map service exists for Venus.
      </div>
      <h2 className="panel-title">Venus — Magellan Global Topographic Data Record (GTDR)</h2>
      <dl className="dl dl--wide">
        <dt>Reference</dt>
        <dd className="mono">{v.coordinateSystem}, R = {v.radiusEquatorial.toLocaleString("en-US")} m</dd>
        <dt>Latitude / longitude</dt>
        <dd>
          {v.latitudeType}; {v.longitudeConvention}, {v.longitudeRange}
        </dd>
        <dt>Resolution</dt>
        <dd>≈ 5 × 5 km/pixel (PDS dataset description)</dd>
        <dt>Projections</dt>
        <dd>{v.projections.join(", ")}</dd>
        <dt>Values</dt>
        <dd className="warn-text">
          GTDR values are planetary radius, not height. The importer rejects radius values as elevation; convert them relative to a
          reference radius first.
        </dd>
        <dt>Status</dt>
        <dd>REQUIRES_USER_DATA — download from PDS and import with import_dem --planet VENUS</dd>
        <dt>Source</dt>
        <dd>
          <a href="https://pds.nasa.gov/ds-view/pds/viewDataset.jsp?dsid=MGN-V-RDRS-5-GDR-TOPOGRAPHIC-V1.0" target="_blank" rel="noreferrer">
            NASA PDS: MGN-V-RDRS-5-GDR-TOPOGRAPHIC-V1.0
          </a>
          <br />
          <a href="https://pds-geosciences.wustl.edu/missions/magellan/gxdr/" target="_blank" rel="noreferrer">
            PDS Geosciences — Magellan GxDR products
          </a>
        </dd>
      </dl>
    </div>
  );
}
