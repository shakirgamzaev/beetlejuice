# Pullin frontend

A Svelte + Vite parking interface for the existing FastAPI backend. No camera or API key is required to explore the explicitly labeled interactive demo.

## Run

Use Node.js 20.19+ and npm:

```sh
cd frontend
npm ci
npm run dev
```

Open http://localhost:5173. Start the existing backend on port 8000 and optionally run `backend/simulate_camera.py` using the backend README. Vite proxies `/api` and `/ws` to the backend. If the backend is unavailable, click **Try interactive demo**. Demo mode is local to the browser and never writes to the backend.

```sh
npm run check
npm test
npm run build
```

## Where to work

- `src/App.svelte`: interface, snapshot polling, live updates, selection and dialogs.
- `src/app.css`: visual design and responsive layouts.
- `src/lib/parking.js`: freshness, ordering and navigation helpers.

## Camera integration

The UI consumes the existing `GET /api/spots` and `/ws/parking` contract without backend changes. Send real camera observations to the existing detection endpoint using stable `spot_id` values. `demo-camera` is a reserved simulator label; use another ID for real observations. Continue sending observations for unchanged spaces, not just transitions.

Because the backend only broadcasts occupancy transitions, the UI also fetches snapshots every five seconds to refresh observation timestamps. Data older than 20 seconds, confidence below 0.6, future timestamps over 10 seconds ahead, and disconnected states display as unknown. Camera clocks must be synchronized. These frontend heuristics do not replace backend stale-state handling or model calibration.

The map models FIU Parking Lot 9 as a zoomable, pannable vector layout. `src/lib/lot9.js` holds the layout, interior row segments, perimeter bays, island outlines, access aisles and parking categories. The current 399 labels are NOT a verified inventory or an official capacity. Blue-marked rows are classified faculty/staff; wheelchair-marked east-edge spaces are classified accessible; Q6–Q12 are temporarily classified metered at $1.50/hour and $8/day; N1–N15 and O1–O14 are temporarily classified admin decal; remaining general spaces are classified FIU student parking permit.

All GPS coordinates are null until georeferencing and field checks. Missing observations show `unmonitored`; existing observations that expire show `unknown`. Incoming IDs must exactly match the provisional map IDs (e.g. `F9`); old `A-1` simulator IDs are intentionally not remapped. The standalone demo exercises eight specifically identified map stalls with an explicit simulated-data banner. Unobserved spaces remain unmonitored in demo mode too.

Labels increase top-to-bottom on each single-sided interior row; perimeter IDs P01–P37 proceed from the northern entrance around the curve toward the southwest. These are Pullin labels, not confirmed onsite signage. Visible traffic arrows are reference geometry only, not a validated internal route graph. The drawing does not provide turn-by-turn stall routing.

## Directions and video

Use the settings button to enter a verified vehicle-entrance latitude/longitude. Available spaces then offer Google Maps directions to that entrance (not a reservation or exact-space indoor navigation). Simulated observations never launch directions, whether they come from the backend simulator or the interactive demo. Do not use fabricated coordinates for a real lot.

An optional camera player URL embeds a browser-compatible page such as MediaMTX WebRTC. RTSP alone is not browser-compatible. Video requires a reachable server, embedding permission, and compatible HTTP/HTTPS configuration. No video player is loaded before configuration.

## Hosting

`npm run build` creates `dist/`. The development proxy is not included in a production build: configure the host to proxy `/api` and `/ws` to FastAPI, or supply `VITE_API_BASE_URL=https://your-api-host` and `VITE_WS_URL=wss://your-api-host/ws/parking` at build time. Add the frontend origin to the backend's `FRONTEND_ORIGINS`. These URLs are public frontend configuration, not secrets.

The UI uses Google Fonts with local sans-serif fallbacks. Lot preferences are stored only in this browser's local storage. No map API key or location permission is requested.
