<script>
  import { onMount } from 'svelte';
  import Icon from './lib/Icon.svelte';
  import LotMap from './lib/LotMap.svelte';
  import { LOT_NAME, lotSpots, mappedObservations, restrictionLabels } from './lib/lot9.js';
  import { DEMO_OCCUPIED_IDS } from './lib/demoSnapshot.js';
  import { statusOf, ageLabel, mergeSpots, validCoordinates, mapsUrl } from './lib/parking.js';

  let spots = [];
  let events = [];
  let now = Date.now();
  let online = false;
  let connection = 'connecting';
  let mode = 'demo';
  let selectedId = '';
  let activeView = 'parking';
  let mapView = 'map';
  let filter = 'all';
  let restrictionFilter = 'all';
  let search = '';
  let dialog;
  let modal = '';
  let cameraExpanded = false;
  let demoSnapshotLoaded = false;
  let error = '';
  let notice = '';
  let config = { name: LOT_NAME, latitude: '', longitude: '', cameraUrl: 'http://3.227.20.110:8889/parking?autoplay=true&muted=true&playsInline=true' };
  let draft = { ...config };
  let stopTransport = () => {};
  const apiBase = (import.meta.env.VITE_API_BASE_URL || 'http://3.227.20.110:8000').replace(/\/$/, '');
  const wsBase = import.meta.env.VITE_WS_URL || (apiBase ? apiBase.replace(/^http/, 'ws') + '/ws/parking' : `${location.protocol === 'https:' ? 'wss:' : 'ws:'}//${location.host}/ws/parking`);

  // Staged demo states are intentionally static until refresh; real camera/API observations still expire.
  function displayStatus(spot, timestamp, connected) {
    if (mode === 'demo' && spot?.camera_id === 'demo-camera' && Number.isFinite(spot.confidence) && spot.confidence >= 0.6 && typeof spot.available === 'boolean') {
      return spot.available ? 'available' : 'occupied';
    }
    return statusOf(spot, timestamp, connected);
  }

  $: enriched = mappedObservations(spots, now, online, displayStatus);
  $: unmonitored = enriched.filter(spot => spot.status === 'unmonitored');
  $: unmapped = spots.filter(spot => !lotSpots.some(layout => layout.spot_id === spot.spot_id));
  $: available = enriched.filter(spot => spot.status === 'available');
  $: occupied = enriched.filter(spot => spot.status === 'occupied');
  $: unknown = enriched.filter(spot => spot.status === 'unknown');
  $: selected = enriched.find(spot => spot.spot_id === selectedId);
  $: filtered = enriched.filter(spot => (filter === 'all' || spot.status === filter) && (restrictionFilter === 'all' || spot.restriction === restrictionFilter) && spot.spot_id.toLowerCase().includes(search.toLowerCase().replace('-', '')));
  $: simulated = mode === 'demo' || spots.some(spot => spot.camera_id === 'demo-camera');
  $: navigationUrl = !simulated && selected?.status === 'available' ? mapsUrl(config.latitude, config.longitude) : null;
  $: latestObservation = spots.length ? spots.reduce((latest, spot) => Date.parse(spot.updated_at) > Date.parse(latest) ? spot.updated_at : latest, spots[0].updated_at) : null;
  $: if (!selectedId) selectedId = available[0]?.spot_id || 'G9';

  function recordUpdates(updates) {
    const changes = updates.filter(spot => spots.find(previous => previous.spot_id === spot.spot_id)?.available !== spot.available);
    events = [...changes.map(spot => ({ ...spot, event_id: `${spot.spot_id}-${spot.updated_at}` })), ...events].slice(0, 30);
    spots = mergeSpots(spots, updates);
  }

  function connectBackend() {
    stopTransport();
    mode = 'backend';
    spots = []; events = []; selectedId = ''; online = false; connection = 'connecting';
    let stopped = false;
    let socket;
    let retry;
    let fetching = false;
    const controllers = new Set();
    async function poll() {
      if (fetching || stopped) return;
      fetching = true;
      const controller = new AbortController();
      controllers.add(controller);
      const timeout = setTimeout(() => controller.abort(), 4000);
      try {
        const response = await fetch(`${apiBase}/api/spots`, { signal: controller.signal });
        if (!response.ok) throw new Error('Unavailable');
        const data = await response.json();
        if (!Array.isArray(data)) throw new Error('Invalid response');
        if (!stopped) { spots = mergeSpots(spots, data); online = true; connection = socket?.readyState === WebSocket.OPEN ? 'live' : 'polling'; }
      } catch {
        if (!stopped) { online = false; connection = 'offline'; }
      } finally { clearTimeout(timeout); controllers.delete(controller); fetching = false; }
    }
    function connect() {
      if (stopped) return;
      try { socket = new WebSocket(wsBase); } catch { retry = setTimeout(connect, 4000); return; }
      socket.onopen = () => { if (!stopped) { connection = 'live'; poll(); } };
      socket.onmessage = event => {
        if (stopped) return;
        try {
          const message = JSON.parse(event.data);
          if (!Array.isArray(message.spots)) return;
          if (message.type === 'parking.snapshot') spots = mergeSpots(spots, message.spots);
          else if (message.type === 'parking.updated') recordUpdates(message.spots);
          online = true; connection = 'live';
        } catch { /* Keep the last valid observation if a message is malformed. */ }
      };
      socket.onclose = () => { if (!stopped) { connection = online ? 'polling' : 'offline'; retry = setTimeout(connect, 3000); } };
      socket.onerror = () => socket.close();
    }
    poll(); connect();
    const polling = setInterval(poll, 5000);
    stopTransport = () => { stopped = true; clearInterval(polling); clearTimeout(retry); controllers.forEach(controller => controller.abort()); if (socket) { socket.onclose = null; socket.close(); } };
  }

  function startDemo() {
    stopTransport();
    mode = 'demo'; connection = 'demo'; online = true; selectedId = ''; events = [];
    spots = lotSpots.filter(s => ['F8','F9','F10','G8','G9','G10','Q1','P01'].includes(s.spot_id)).map((layout, i) => ({ spot_id: layout.spot_id, available: ![1, 4, 6].includes(i), confidence: 0.96, camera_id: 'demo-camera', updated_at: new Date().toISOString() }));
    let tick = 0;
    const timer = setInterval(() => {
      const updated = spots.map((spot, i) => ({ ...spot, available: i === tick % spots.length ? !spot.available : spot.available, updated_at: new Date().toISOString() }));
      recordUpdates(updated); tick++;
    }, 7000);
    stopTransport = () => clearInterval(timer);
    dialog?.close();
  }

  function startVacantDemo() {
    stopTransport();
    mode = 'demo'; connection = 'demo'; online = true; events = []; selectedId = '';
    demoSnapshotLoaded = false;
    const updatedAt = new Date().toISOString();
    spots = lotSpots.map(layout => ({ spot_id: layout.spot_id, available: true, confidence: 1, camera_id: 'demo-camera', updated_at: updatedAt }));
  }

  function loadDemoSnapshot() {
    if (mode !== 'demo' || demoSnapshotLoaded) return;
    stopTransport();
    const updatedAt = new Date().toISOString();
    const snapshot = lotSpots.map(layout => ({ spot_id: layout.spot_id, available: !DEMO_OCCUPIED_IDS.has(layout.spot_id), confidence: 1, camera_id: 'demo-camera', updated_at: updatedAt }));
    recordUpdates(snapshot);
    demoSnapshotLoaded = true;
  }

  function toggleCamera() {
    cameraExpanded = !cameraExpanded;
    if (cameraExpanded) loadDemoSnapshot();
  }

  function openModal(type) { modal = type; error = ''; draft = { ...config }; dialog.showModal(); }
  function saveSettings(event) {
    event.preventDefault();
    if ((draft.latitude || draft.longitude) && !validCoordinates(draft.latitude, draft.longitude)) { error = 'Enter a valid latitude (−90 to 90) and longitude (−180 to 180), or leave both blank.'; return; }
    if (draft.cameraUrl) {
      try { const url = new URL(draft.cameraUrl); if (!['http:', 'https:'].includes(url.protocol)) throw new Error(); }
      catch { error = 'The camera player needs a complete http:// or https:// URL.'; return; }
    }
    config = { ...draft, name: LOT_NAME };
    try { localStorage.setItem('pullin-lot9', JSON.stringify(config)); } catch { /* Settings still work for this visit. */ }
    notice = 'Lot settings saved.'; dialog.close();
  }
  function chooseSpot(spot) { selectedId = spot.spot_id; notice = ''; }
  function chooseAvailable() {
    if (available.length) { selectedId = available[0].spot_id; filter = 'available'; search = ''; activeView = 'parking'; notice = `Space ${selectedId} is selected. Availability is not a reservation.`; }
  }

  onMount(() => {
    try {
      const saved = JSON.parse(localStorage.getItem('pullin-lot9') || 'null');
      if (saved && typeof saved === 'object') config = { ...config, ...Object.fromEntries(Object.entries(saved).filter(([key, value]) => key in config && typeof value === 'string')) };
    } catch { /* Ignore damaged local preferences. */ }
    config.name = LOT_NAME;
    startVacantDemo();
    const clock = setInterval(() => now = Date.now(), 1000);
    return () => { stopTransport(); clearInterval(clock); };
  });
</script>

<svelte:head><title>Pullin — Find your space.</title></svelte:head>

<header class="site-header">
  <button class="brand" aria-label="Pullin home" onclick={() => activeView = 'parking'}><span class="brand-mark">p<span></span></span>pullin<span class="brand-period">.</span></button>
  <nav aria-label="Main navigation">
    <button class:nav-active={activeView === 'parking'} onclick={() => activeView = 'parking'}>Find parking</button>
    <button class:nav-active={activeView === 'activity'} onclick={() => activeView = 'activity'}>Live activity</button>
    <button onclick={() => openModal('about')}>How it works <Icon name="external" size={13}/></button>
  </nav>
  <div class="header-right"><span class="project-tag">A little less circling.</span><button class="icon-button settings-trigger" aria-label="Lot settings" onclick={() => openModal('settings')}><Icon name="settings"/></button></div>
</header>

<main>
  <section class="intro">
    <div><div class="eyebrow"><span class="tiny-line"></span> A BETTER WAY TO ARRIVE</div><h1>Less circling.<br class="mobile-break"/> <span>More living.</span></h1><p>Your next open space, a little easier to find.</p></div>
    <div class="intro-note"><span class="orbit"><Icon name="leaf" size={23}/></span><div>Make room for<br/><strong>what matters.</strong></div></div>
  </section>

  <div class="location-bar">
    <button class="location-picker" onclick={() => openModal('settings')}><span class="location-icon"><Icon name="pin" size={21}/></span><span><small>YOUR PARKING LOCATION</small><strong>{config.name}</strong></span><Icon name="chevron" size={17}/></button>
    <div class="location-meta"><span class="status-dot" class:offline={!online}></span><span>{connection === 'connecting' ? 'Connecting…' : !online ? 'Connection unavailable' : unmonitored.length === enriched.length ? 'Lot mapped · camera setup pending' : spots.length && unknown.length === spots.length ? 'Waiting for fresh observations' : connection === 'polling' ? 'Updating every 5 seconds' : 'Availability connected'}</span></div>
    <button class="subtle-button" aria-expanded={cameraExpanded} onclick={toggleCamera}><Icon name="camera" size={17}/> {cameraExpanded ? 'Hide camera' : 'Show camera'} <Icon name="chevron" size={14}/></button>
  </div>

  {#if cameraExpanded}
    <section class="camera-section" aria-label="Live parking camera">
      <div class="camera-section-heading"><div><span class="section-overline">LIVE CAMERA</span><h2>Watch the lot change.</h2><p>Keep this view open while the mapped spaces update.</p></div><button class="secondary" onclick={() => openModal('settings')}><Icon name="settings" size={15}/> Configure feed</button></div>
      {#if config.cameraUrl && /^https?:\/\//.test(config.cameraUrl)}
        <iframe src={config.cameraUrl} title="Live FIU Lot 9 parking camera" class="camera-player-inline" allow="autoplay; fullscreen" sandbox="allow-scripts allow-same-origin"></iframe>
      {:else}
        <div class="camera-placeholder-inline"><Icon name="camera" size={34}/><div><strong>Camera feed not connected yet</strong><p>Paste a browser-compatible WebRTC or HLS player URL in Lot settings. RTSP URLs cannot play directly in a browser.</p></div><button class="secondary" onclick={() => openModal('settings')}>Add camera URL <Icon name="arrow" size={15}/></button></div>
      {/if}
      <div class="camera-section-foot"><span><i class="status-dot" class:offline={!online}></i>{mode === 'demo' ? (demoSnapshotLoaded ? 'Occupancy updated' : 'All spaces start vacant') : online ? 'Occupancy updates connected' : 'Waiting for occupancy service'}</span></div>
    </section>
  {/if}

  {#if simulated}
    <div class="demo-banner"><span><span class="demo-tag">DEMO</span> {mode === 'demo' ? (demoSnapshotLoaded ? 'Image-based occupancy snapshot. Demo only; not live detection.' : 'Vacant demo baseline. Show camera to load the occupied-space snapshot.') : 'Connected to the camera simulator. These are not real parking observations.'}</span><button onclick={() => mode === 'demo' ? connectBackend() : openModal('about')}>{mode === 'demo' ? 'Connect live backend' : 'About this demo'} <Icon name="arrow" size={14}/></button></div>
  {:else if !online && connection !== 'connecting'}
    <div class="demo-banner disconnected"><span><Icon name="info" size={17}/> We can’t reach the parking service. Previous observations are shown as unknown.</span><button onclick={startDemo}>Try interactive demo <Icon name="arrow" size={14}/></button></div>
  {/if}

  <div class="workspace">
    <section class="map-panel" aria-label="Parking availability">
      <div class="panel-heading"><div><h2>{activeView === 'activity' ? 'The latest in the lot' : 'A space for your next stop.'}</h2><p>{activeView === 'activity' ? 'Occupancy changes observed during this visit.' : 'FIU Lot 9 layout · provisional labels · zoom to inspect.'}</p></div><div class="view-toggle" aria-label="Parking view"><button class:chosen={mapView === 'map'} aria-label="Map view" aria-pressed={mapView === 'map'} onclick={() => { mapView = 'map'; activeView = 'parking'; }}><Icon name="grid" size={17}/></button><button class:chosen={mapView === 'list'} aria-label="List view" aria-pressed={mapView === 'list'} onclick={() => { mapView = 'list'; activeView = 'parking'; }}><Icon name="list" size={18}/></button></div></div>

      {#if activeView === 'activity'}
        <div class="activity-list">
          {#each events as event, i (`${event.event_id}-${i}`)}<div class="activity-row"><span class="event-icon" class:vacated={event.available}><Icon name={event.available ? 'arrow' : 'car'} size={19}/></span><div><strong>Space {event.spot_id}</strong><p>{event.available ? 'Became available' : 'Became occupied'}{simulated ? ' · simulated' : ''}</p></div><time>{ageLabel(event.updated_at, now)}</time></div>
          {:else}<div class="empty-state"><Icon name="clock" size={34}/><h3>Every arrival has a story.</h3><p>New occupancy changes will appear here.<br/>Keep this page open while spaces update.</p></div>{/each}
        </div>
      {:else}
        <div class="filter-bar"><div class="filter-buttons"><button class:active={filter === 'all'} onclick={() => filter = 'all'}>All spaces <span>{enriched.length}</span></button><button class:active={filter === 'available'} onclick={() => filter = 'available'}><span class="mini-dot"></span>Available <span>{available.length}</span></button></div><label class="space-search"><Icon name="pin" size={15}/><input aria-label="Find a space by ID" placeholder="Find a space" bind:value={search}/></label></div>
        <div class="lot-restrictions"><label>Space type <select aria-label="Filter space type" bind:value={restrictionFilter}><option value="all">All types</option><option value="staff">Faculty / staff</option><option value="accessible">Accessible</option><option value="metered">Metered</option><option value="admin">Admin decal</option><option value="unverified">FIU student parking permit</option></select></label><span>Blue edge: faculty/staff · ♿: accessible · $: metered</span></div>
        <p class="lot-review-note">Parking rules and labels are provisional until confirmed onsite.</p>
        {#if unmapped.length && mode !== 'demo'}<div class="lot-integration-note">The current camera feed isn’t mapped to Lot 9 yet. Unobserved spaces stay “Not monitored.” <button onclick={startDemo}>Preview a few simulated spaces →</button></div>{/if}
        {#if mapView === 'map'}
          <LotMap spots={enriched} {selectedId} visibleIds={filtered.map(s => s.spot_id)} onselect={chooseSpot}/>

        {:else}
          <div class="spaces-list">{#each filtered as spot (spot.spot_id)}<button class="space-list-row" class:row-selected={selectedId === spot.spot_id} onclick={() => chooseSpot(spot)}><span class="list-parking-icon {spot.status}">P</span><span><strong>Space {spot.spot_id}</strong><small>{restrictionLabels[spot.restriction]} · {spot.status === "unmonitored" ? "Not monitored" : ageLabel(spot.updated_at, now)}</small></span><span class="status-label {spot.status}">{spot.status}</span><Icon name="arrow" size={17}/></button>{:else}<div class="empty-state"><Icon name="pin" size={32}/><h3>No matching spaces</h3><p>Try a different space ID or switch to all spaces.</p></div>{/each}</div>
        {/if}
        {#if search && !filtered.length && mapView === 'map'}<p class="search-note" role="status">No spaces match “{search}”. Try another space ID.</p>{/if}
        <div class="map-footer"><div class="legend"><span><i class="available"></i>Available</span><span><i class="occupied"></i>Occupied</span><span><i class="unknown"></i>Unknown</span><span><i class="unmonitored"></i>Not monitored</span></div><span class="map-hint">Select a space to explore <Icon name="arrow" size={14}/></span></div>
      {/if}
    </section>

    <aside class="side-panel">
      <section class="availability-card"><div class="card-eyebrow"><span class="status-dot" class:offline={!online}></span> {simulated ? 'DEMO AVAILABILITY' : 'PARKING AT A GLANCE'}<Icon name="bolt" size={16}/></div><div class="availability-number">{available.length}<span>/ {enriched.length} spaces</span></div><h2>A little room to breathe.</h2><p>{available.length ? 'Open spaces, without the guessing game.' : spots.length ? 'No mapped spaces confirmed open.' : 'Waiting for the first parking observation.'}</p><p class="monitoring-count">{unmonitored.length} mapped spaces not monitored</p><div class="capacity-bar" aria-label={`${available.length} available, ${occupied.length} occupied, ${unknown.length} unknown`} >{#each enriched as spot}<span class={spot.status}></span>{/each}</div><div class="availability-foot"><span>{occupied.length} occupied · {unknown.length} unknown</span><span><Icon name="clock" size={12}/>{latestObservation ? ageLabel(latestObservation, now) : 'Waiting'}</span></div></section>

      <section class="selection-card"><div class="section-overline">YOUR NEXT STOP</div>
        {#if selected}
          <div class="selected-heading"><div><h2>Space {selected.spot_id}</h2><p>{config.name}</p></div><span class="selected-pin"><Icon name="pin" size={24}/></span></div>
          <span class="selected-status {selected.status}"><span class="mini-dot"></span>{selected.status === 'available' ? 'Available now' : selected.status === 'occupied' ? 'Currently occupied' : selected.status === 'unmonitored' ? 'Not monitored' : 'Availability unknown'}</span>
          <div class="space-facts"><div><Icon name="info" size={17}/><span>Space type</span><strong>{restrictionLabels[selected.restriction]}</strong></div><div><Icon name="pin" size={17}/><span>Layout</span><strong>{selected.parallel ? "Perimeter parallel" : "Interior stall"}</strong></div><div><Icon name="clock" size={17}/><span>Last observed</span><strong>{ageLabel(selected.updated_at, now)}</strong></div><div><Icon name="camera" size={17}/><span>Source</span><strong>{selected.status === 'unmonitored' ? 'No camera assigned' : selected.camera_id === 'demo-camera' ? 'Simulator' : 'Camera observation'}</strong></div></div>
          {#if selected.status === 'unmonitored'}<p class="selection-message">This space is mapped, but has no camera observation. Its availability is not known.</p>{:else if selected.status === 'occupied'}<p class="selection-message" role="status">This space is occupied. Choose another available space before heading over.</p>{:else if selected.status === 'unknown'}<p class="selection-message" role="status">We can’t confirm this space right now. Wait for a fresh observation.</p>{/if}
          {#if navigationUrl}<a class="primary" href={navigationUrl} target="_blank" rel="noopener noreferrer"><Icon name="compass" size={18}/> Navigate to lot <Icon name="arrow" size={17}/></a>{:else}<button class="primary" disabled={selected.status !== 'available'} onclick={() => openModal(simulated ? 'demo-route' : 'settings')}><Icon name="compass" size={18}/>{selected.status !== 'available' ? 'Choose an open space' : simulated ? 'Explore arrival' : 'Set lot entrance'}<Icon name="arrow" size={17}/></button>{/if}
          <p class="field-help">Provisional ID · {selected.review}</p><p class="reservation-note">{navigationUrl ? 'Directions lead to the lot entrance.' : 'Real directions need a verified lot entrance.'}<br/>Availability is an observation, not a reservation.</p>
        {:else}<div class="no-selection"><Icon name="pin" size={32}/><h2>Your space is out there.</h2><p>Select a parking space on the map to see its latest status.</p></div>{/if}
      </section>

      <section class="tip-card"><span class="tip-icon"><Icon name="leaf" size={22}/></span><div><h3>Less searching. More arriving.</h3><p>Live observations help you make your next move with a little more clarity.</p></div></section>
    </aside>
  </div>

  <section class="bottom-strip"><div><span class="small-brand-mark">p.</span><div><strong>A smarter start to your next stop.</strong><p>See a space. Pick your spot. Pull in.</p></div></div><button onclick={chooseAvailable} disabled={!available.length}>Find an open space <Icon name="arrow" size={18}/></button></section>
  {#if notice}<div class="notice" role="status"><Icon name="check" size={17}/>{notice}<button aria-label="Dismiss message" onclick={() => notice = ''}><Icon name="close" size={15}/></button></div>{/if}
  <footer><span>pullin. <span>Made for better arrivals.</span></span><button onclick={() => openModal('about')}>Built for ShellHacks <span>↗</span></button></footer>
</main>

<dialog bind:this={dialog} class="modal" aria-labelledby="modal-title">
  <div class="modal-top"><span class="section-overline">PULLIN</span><button class="icon-button" aria-label="Close dialog" onclick={() => dialog.close()}><Icon name="close"/></button></div>
  {#if modal === 'settings'}
    <h2 id="modal-title">Make it your lot.</h2><p class="modal-description">Connect the experience to the place you’re monitoring. Settings are saved in this browser.</p>
    <form onsubmit={saveSettings}><label>Lot name<input readonly bind:value={draft.name} maxlength="80" placeholder="e.g. Campus lot A" required/></label><div class="form-columns"><label>Entrance latitude<input bind:value={draft.latitude} placeholder="e.g. 25.756" inputmode="decimal"/></label><label>Entrance longitude<input bind:value={draft.longitude} placeholder="e.g. −80.374" inputmode="decimal"/></label></div><p class="field-help">Use the verified vehicle entrance, not the center of the lot. Leave blank until your team confirms it.</p><label>Camera player URL <span>(optional)</span><input bind:value={draft.cameraUrl} placeholder="https://your-camera-host/parking" type="url"/></label><p class="field-help">A browser-compatible player, such as your MediaMTX WebRTC page. An RTSP URL cannot play directly in the browser.</p>{#if error}<p class="form-error" role="alert">{error}</p>{/if}<button class="primary" type="submit">Save lot settings <Icon name="check" size={17}/></button></form>
  {:else if modal === 'camera'}
    <h2 id="modal-title">A new perspective.</h2><p class="modal-description">The camera behind your parking observations.</p>
    {#if config.cameraUrl && /^https?:\/\//.test(config.cameraUrl)}<iframe src={config.cameraUrl} title="Parking camera player" class="camera-player" sandbox="allow-scripts allow-same-origin" allow="autoplay; fullscreen"></iframe><p class="field-help">If the feed is blank, check that the camera host is reachable and allows embedding.</p>{:else}<div class="camera-placeholder"><Icon name="camera" size={44}/><h3>Your camera goes here.</h3><p>The live feed hasn’t been connected yet.<br/>Your parking interface is ready when it is.</p><button class="secondary" onclick={() => openModal('settings')}>Connect a camera <Icon name="arrow" size={16}/></button></div>{/if}
  {:else if modal === 'demo-route'}
    <h2 id="modal-title">From open space to arrival.</h2><p class="modal-description">This is the Lot 9 layout with simulated observations. Individual space coordinates have not been verified.</p><div class="journey-step"><span>1</span><div><strong>Choose an available space</strong><p>You’ve selected {selectedId}. Watch its status update live.</p></div></div><div class="journey-step"><span>2</span><div><strong>Navigate to the real lot entrance</strong><p>Once configured, Pullin opens driving directions in Google Maps.</p></div></div><div class="journey-step"><span>3</span><div><strong>Find your space in the lot</strong><p>Use the space label and the verified lot layout. Availability can change before you arrive.</p></div></div><button class="primary" onclick={() => dialog.close()}>Back to the lot <Icon name="arrow" size={17}/></button>
  {:else}
    <h2 id="modal-title">Less circling starts here.</h2><p class="modal-description">Pullin turns parking observations into a clearer picture of where you can go next.</p><div class="journey-step"><span><Icon name="camera" size={19}/></span><div><strong>A camera watches the spaces</strong><p>The vision system identifies occupied and vacant spaces, then sends observations to Pullin.</p></div></div><div class="journey-step"><span><Icon name="bolt" size={19}/></span><div><strong>Your view stays up to date</strong><p>Changes arrive automatically. Disconnected, low-confidence, or observations older than 20 seconds become unknown.</p></div></div><div class="journey-step"><span><Icon name="compass" size={19}/></span><div><strong>You find your next stop</strong><p>Select a space and navigate to a verified lot entrance. Spaces are never reserved by selecting them.</p></div></div><div class="about-demo"><strong>Currently a hackathon prototype</strong><p>The Lot 9 drawing and parking categories are awaiting onsite confirmation. Simulator data is labeled; real camera detection and a surveyed lot layout are separate integrations.</p></div><button class="secondary" onclick={startDemo}><Icon name="play" size={16}/> Try interactive demo</button>
  {/if}
</dialog>
