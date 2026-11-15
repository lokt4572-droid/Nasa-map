# v0.5 phase 5 — ZIP, pages, Earth 2D (2026-11-15, local dev servers)

| Check | Result | How |
|---|---|---|
| ZIP with a waypoint, 3 hazards, a route | PASS | `src/offline/packageRoundTrip.test.ts` (disposable test mission): waypoint kept in `mission/mission.json`, all 3 mission hazards in `hazards/hazards.json`, another mission's hazard excluded, route in `routes/routes.json`, SHA-256 manifest valid |
| Duplicate import | PASS | importing the same package twice creates no mission or hazard (client_id replay) |
| Planned route included in the exported ZIP | FIXED | `OfflinePanel` previously exported `routes/routes.json` empty; it now includes the currently planned route as computed (geometry, metrics, validation) |
| `/` landing | PASS | renders, title "Nova" |
| `/rover/` | PASS | renders, title "Curiosity rover — Nova" |
| `/map/` | PASS | renders, title "Map — Nova" |
| Planet switching Mars → Moon → Mercury → Earth → Mars (UI) | PASS | no crash; each body gets its default layer |
| Earth 2D map | PASS | OpenStreetMap basemap renders, measure and search tools present |
| Geolocation | PASS (denied path) | the browser pane denies location; the app shows PERMISSION_DENIED with instructions and does nothing else. The granted path was not testable here |

Not checked: geolocation with permission granted (needs a real browser/device).
