export const STALE_AFTER_MS = 20_000;

export function statusOf(spot, now = Date.now(), connected = true) {
  const observed = Date.parse(spot?.updated_at);
  if (!connected || !Number.isFinite(observed) || now - observed > STALE_AFTER_MS || observed - now > 10_000 || !Number.isFinite(spot?.confidence) || spot.confidence < 0.6) return 'unknown';
  return spot?.available === true ? 'available' : spot?.available === false ? 'occupied' : 'unknown';
}

export function ageLabel(time, now = Date.now()) {
  const age = Math.max(0, Math.floor((now - Date.parse(time)) / 1000));
  if (!Number.isFinite(age)) return 'Not observed yet';
  if (age < 3) return 'Just now';
  if (age < 60) return `${age}s ago`;
  if (age < 3600) return `${Math.floor(age / 60)}m ago`;
  return `${Math.floor(age / 3600)}h ago`;
}

export function mergeSpots(current, updates) {
  const merged = new Map(current.map(spot => [spot.spot_id, spot]));
  for (const spot of updates) {
    if (typeof spot.spot_id !== 'string' || !Number.isFinite(Date.parse(spot.updated_at))) continue;
    const previous = merged.get(spot.spot_id);
    if (!previous || Date.parse(spot.updated_at) >= Date.parse(previous.updated_at)) merged.set(spot.spot_id, spot);
  }
  return [...merged.values()].sort((a, b) => a.spot_id.localeCompare(b.spot_id, undefined, { numeric: true }));
}

export function validCoordinates(lat, lng) {
  return String(lat).trim() !== '' && String(lng).trim() !== '' && Number.isFinite(Number(lat)) && Number.isFinite(Number(lng)) && Math.abs(Number(lat)) <= 90 && Math.abs(Number(lng)) <= 180;
}

export function mapsUrl(lat, lng) {
  if (!validCoordinates(lat, lng)) return null;
  return `https://www.google.com/maps/dir/?api=1&destination=${encodeURIComponent(`${Number(lat)},${Number(lng)}`)}&travelmode=driving`;
}
