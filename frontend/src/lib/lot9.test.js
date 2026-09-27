import test from 'node:test';
import assert from 'node:assert/strict';
import {lotSpots, exclusions, mappedObservations} from './lot9.js';
import {statusOf} from './parking.js';
test('map identities are unique and coordinates are not invented',()=>{
  assert.equal(new Set(lotSpots.map(s=>s.spot_id)).size,lotSpots.length);
  assert.ok(lotSpots.every(s=>s.latitude===null&&s.longitude===null));
  assert.ok(lotSpots.some(s=>s.parallel));
  assert.ok(lotSpots.some(s=>s.restriction==='accessible'));
});
test('access aisles cannot become selectable parking stalls',()=>{
  for(const e of exclusions)for(const s of lotSpots.filter(s=>!s.parallel)) {
    assert.ok(!(s.x<e.x+e.width&&s.x+s.width>e.x&&s.y<e.y+e.height&&s.y+s.height>e.y),`${s.spot_id} overlaps access aisle`);
  }
});
test('old simulator labels cannot claim availability for Lot 9',()=>{
  const now=Date.now();
  const observation={spot_id:'A-1',available:true,confidence:.95,updated_at:new Date(now).toISOString()};
  assert.ok(mappedObservations([observation],now,true,statusOf).every(s=>s.status==='unmonitored'));
  const actual=mappedObservations([{...observation,spot_id:'F9'}],now,true,statusOf);
  assert.equal(actual.find(s=>s.spot_id==='F9').status,'available');
  assert.equal(actual.find(s=>s.spot_id==='F10').status,'unmonitored');
  assert.equal(mappedObservations([{...observation,spot_id:'F9'}],now+21000,true,statusOf).find(s=>s.spot_id==='F9').status,'unknown');
});
