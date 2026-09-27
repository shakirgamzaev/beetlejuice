import test from 'node:test';
import assert from 'node:assert/strict';
import { statusOf, mergeSpots, validCoordinates, mapsUrl } from './parking.js';

const now = Date.now();
const spot = { spot_id: 'A-1', available: true, confidence: 0.95, updated_at: new Date(now).toISOString() };
test('stale, disconnected, low confidence, missing and future observations are never available', () => {
  assert.equal(statusOf(spot, now), 'available');
  assert.equal(statusOf(spot, now + 21_000), 'unknown');
  assert.equal(statusOf(spot, now, false), 'unknown');
  assert.equal(statusOf({ ...spot, confidence: 0.2 }, now), 'unknown');
  assert.equal(statusOf({}, now), 'unknown');
  assert.equal(statusOf(spot, now - 30_000), 'unknown');
  assert.equal(statusOf({ ...spot, available: false }, now), 'occupied');
});
test('late snapshots cannot roll back newer websocket observations', () => {
  const old = { ...spot, available: false, updated_at: new Date(now - 5000).toISOString() };
  assert.equal(mergeSpots([spot], [old])[0].available, true);
  assert.equal(mergeSpots([old], [spot])[0].available, true);
});
test('navigation requires real, bounded coordinates, including valid zero', () => {
  assert.equal(validCoordinates('', ''), false);
  assert.equal(validCoordinates('91', '20'), false);
  assert.equal(validCoordinates('0', '0'), true);
  assert.equal(mapsUrl('', ''), null);
  assert.match(mapsUrl('25.75', '-80.37'), /destination=25.75%2C-80.37/);
});
