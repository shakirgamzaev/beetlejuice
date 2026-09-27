<script>
  import {lotBoundary, islands, exclusions, restrictionLabels} from './lot9.js';
  export let spots = [];
  export let selectedId = '';
  export let visibleIds = [];
  export let onselect = () => {};
  let zoom = 1;
  let cx = 886.5;
  let cy = 703.5;
  let dragging = null;
  $: vw = 1850 / zoom;
  $: vh = 1480 / zoom;
  function scale(factor) { zoom = Math.max(1, Math.min(6, zoom*factor)); if (zoom === 1) reset(); }
  function reset() { zoom=1; cx=886.5; cy=703.5; }
  function focusSelected() { const s=spots.find(s=>s.spot_id===selectedId); if(s) {zoom=3;cx=s.x+s.width/2;cy=s.y+s.height/2;} }
  function start(event) {
    if (event.button !== 0 || event.target.closest('[data-spot]')) return;
    dragging = {x:event.clientX,y:event.clientY,cx,cy,width:event.currentTarget.clientWidth,height:event.currentTarget.clientHeight};
    event.currentTarget.setPointerCapture(event.pointerId);
  }
  function move(event) { if(!dragging)return; cx=Math.max(0,Math.min(1773,dragging.cx-(event.clientX-dragging.x)*vw/dragging.width));cy=Math.max(0,Math.min(1407,dragging.cy-(event.clientY-dragging.y)*vh/dragging.height)); }
  function key(event) { const d=100/zoom; if(event.key==='ArrowLeft')cx-=d;else if(event.key==='ArrowRight')cx+=d;else if(event.key==='ArrowUp')cy-=d;else if(event.key==='ArrowDown')cy+=d;else if(event.key==='+')scale(1.5);else if(event.key==='-')scale(1/1.5);else return;event.preventDefault(); }
</script>
<div class="lot-map-shell">
  <div class="lot-map-toolbar"><span><b>LOT 9</b> · Interactive parking map</span><div><button aria-label="Zoom out" disabled={zoom<=1} onclick={()=>scale(1/1.5)}>−</button><output aria-label="Map zoom">{Math.round(zoom*100)}%</output><button aria-label="Zoom in" disabled={zoom>=6} onclick={()=>scale(1.5)}>+</button><button onclick={reset}>Fit lot</button><button onclick={focusSelected} disabled={!selectedId}>Find selected</button></div></div>
  <!-- svelte-ignore a11y_no_noninteractive_tabindex a11y_no_noninteractive_element_interactions (The map application supports keyboard panning and pointer dragging.) -->
  <div class="lot-map-viewport" role="application" aria-label="FIU Lot 9 map. Use plus and minus buttons to zoom. Drag or use arrow keys to pan." tabindex="0" onkeydown={key} onpointerdown={start} onpointermove={move} onpointerup={()=>dragging=null} onpointercancel={()=>dragging=null}>
    <svg viewBox={`${cx-vw/2} ${cy-vh/2} ${vw} ${vh}`} aria-label="Reconstructed parking layout for FIU Lot 9">
      <defs><pattern id="excluded-lines" width="10" height="10" patternUnits="userSpaceOnUse" patternTransform="rotate(40)"><rect width="10" height="10" fill="#f6f2dd"/><path d="M0 0V10" stroke="#b7a573" stroke-width="3"/></pattern></defs>
      <rect x="-5000" y="-5000" width="10000" height="10000" fill="#e9eee1"/>
      <path d={lotBoundary} fill="#f8f8f2" stroke="#b6c1a5" stroke-width="5"/>
      {#each islands as d}<path {d} fill="#d3dfbd" stroke="#abbc8f" stroke-width="2.5"/>{/each}
      {#each [[367,705],[364,1005],[551,542],[551,833],[750,457],[748,757],[941,411],[939,679],[1130,379],[1130,622],[1320,407],[1320,599],[1519,435],[1520,577]] as [x,y]}
        <circle cx={x-17} cy={y-2} r="18" fill="#bccda6"/><circle cx={x+16} cy={y+1} r="14" fill="#c1d2ab"/>
      {/each}
      {#each exclusions as area}<rect {...area} fill="url(#excluded-lines)" stroke="#c9bb93" stroke-width="1.5"/>{/each}
      <path d="M1426 117L1465 127L1448 151L1408 137Z" fill="url(#excluded-lines)" stroke="#c9bb93"/>
      <path d="M115 1328L130 1375L155 1371L139 1320Z" fill="url(#excluded-lines)"/>
      {#each spots as spot (spot.spot_id)}
        <g data-spot={spot.spot_id} role="button" tabindex="0" aria-label={`${spot.spot_id}, ${restrictionLabels[spot.restriction]}, ${spot.status}`} aria-pressed={selectedId===spot.spot_id} transform={`rotate(${spot.angle} ${spot.x+spot.width/2} ${spot.y+spot.height/2})`} class="stall {spot.status} {spot.restriction}" class:chosen-stall={selectedId===spot.spot_id} class:faded={!visibleIds.includes(spot.spot_id)} onclick={()=>onselect(spot)} onkeydown={event=>{if(event.key==='Enter'||event.key===' '){event.preventDefault();event.stopPropagation();onselect(spot);}}}>
          <title>{spot.spot_id} · {restrictionLabels[spot.restriction]} · {spot.status} · {spot.review}</title>
          <rect x={spot.x} y={spot.y} width={spot.width} height={spot.height} rx="2"/>
          {#if spot.restriction==='staff'}<path d={`M${spot.x+3} ${spot.y+3}v${spot.height-6}`} stroke="#4885a8" stroke-width="3"/>{/if}
          <text x={spot.x+spot.width/2} y={spot.y+spot.height/2+3} text-anchor="middle" font-size="10" font-weight={selectedId===spot.spot_id?'800':'500'} transform={`rotate(${-spot.angle} ${spot.x+spot.width/2} ${spot.y+spot.height/2})`}>{spot.restriction==='accessible'?'♿ ':''}{spot.spot_id}</text>
        </g>
      {/each}
      {#each [[270,880,'A'],[450,690,'B · C'],[649,570,'D · E'],[842,537,'F · G'],[1032,489,'H · I'],[1218,490,'J · K'],[1420,494,'L · M'],[1607,630,'N · O']] as [x,y,label]}
        <text {x} {y} fill="#9ba68e" font-size="15" text-anchor="middle" transform={`rotate(-90 ${x} ${y})`}>{label}</text>
      {/each}
      <text x="485" y="90" fill="#8c9c7b" font-size="19" transform="rotate(-33 485 90)">SW 10TH ST</text>
    </svg>
  </div>
  <div class="lot-map-foot"><span>Provisional Pullin IDs · no GPS alignment yet</span><span>Drag to pan · + to read labels</span></div>
</div>
<style>
.lot-map-shell{background:#e9eee1}.lot-map-toolbar{display:flex;justify-content:space-between;gap:10px;padding:12px 15px;background:#f4f6ee;align-items:center;border-top:1px solid #e3e8d9;font-size:10px;color:#7b896c}.lot-map-toolbar b{color:#395b3c}.lot-map-toolbar>div{display:flex;align-items:center;gap:4px}.lot-map-toolbar button{border:1px solid #dce3d0;border-radius:5px;background:white;padding:7px 9px;font-size:10px}.lot-map-toolbar output{min-width:38px;text-align:center}.lot-map-viewport{width:100%;height:640px;touch-action:none;cursor:grab;overflow:hidden}.lot-map-viewport:active{cursor:grabbing}.lot-map-viewport>svg{display:block;width:100%;height:100%;font-family:'DM Sans',sans-serif}.stall{cursor:pointer;outline:none}.stall rect{fill:#e8ebe2;stroke:#aeb8a1;stroke-width:1.1}.stall text{fill:#637157;pointer-events:none}.stall.staff rect{fill:#e4edf0;stroke:#95afba}.stall.accessible rect{fill:#dbe9f4;stroke:#8aa9c2}.stall.metered rect{fill:#f4e7c7;stroke:#c69b45}.stall.admin rect{fill:#e8e0ee;stroke:#9b80a9}.stall.available rect{fill:#d2e7b9;stroke:#7ca664}.stall.available.staff rect{fill:#e4edf0;stroke:#95afba}.stall.available.accessible rect{fill:#dbe9f4;stroke:#8aa9c2}.stall.available.metered rect{fill:#f4e7c7;stroke:#c69b45}.stall.available.admin rect{fill:#e8e0ee;stroke:#9b80a9}.stall.occupied rect{fill:#e76b66;stroke:#b93432}.stall.occupied text{fill:#fff}.stall.unknown rect{fill:#efe8d7;stroke:#c3b491}.stall.chosen-stall rect,.stall:focus-visible rect{stroke:#163e31;stroke-width:4}.stall.chosen-stall text{fill:#163e31}.stall.occupied.chosen-stall text{fill:#fff}.stall:hover rect{stroke:#315e43;stroke-width:3}.stall.faded{opacity:.16}.lot-map-foot{padding:10px 15px;display:flex;justify-content:space-between;gap:10px;font-size:9px;color:#7c8b6c;border-top:1px solid #dfe6d4}@media(max-width:520px){.lot-map-toolbar{flex-wrap:wrap}.lot-map-toolbar>div{width:100%;justify-content:space-between}.lot-map-toolbar button{min-height:36px}.lot-map-viewport{height:460px}.lot-map-foot{font-size:8px}.lot-map-foot span:last-child{display:none}}
</style>
