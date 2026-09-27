<script>
  export let name = 'arrow';
  export let size = 20;
  const paths = {
    arrow: 'M5 12h14m-6-6 6 6-6 6',
    pin: 'M20 10c0 6-8 11-8 11S4 16 4 10a8 8 0 1 1 16 0ZM15 10a3 3 0 1 1-6 0 3 3 0 0 1 6 0Z',
    grid: 'M3 3h7v7H3ZM14 3h7v7h-7ZM3 14h7v7H3ZM14 14h7v7h-7Z',
    list: 'M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01',
    clock: 'M12 8v5l3 2M22 12a10 10 0 1 1-20 0 10 10 0 0 1 20 0Z',
    camera: 'M3 7h12v12H3ZM15 11l6-3v10l-6-3M6 4h6',
    close: 'm6 6 12 12M6 18 18 6',
    check: 'm5 12 4 4L19 6',
    chevron: 'm8 10 4 4 4-4',
    compass: 'm16 8-3 5-5 3 3-5ZM22 12a10 10 0 1 1-20 0 10 10 0 0 1 20 0Z',
    info: 'M12 11v6M12 7h.01M22 12a10 10 0 1 1-20 0 10 10 0 0 1 20 0Z',
    car: 'm5 7 2-4h10l2 4M3 8h18v10H3ZM5 18v3M19 18v3M6 12h2M16 12h2',
    play: 'm8 4 12 8-12 8Z',
    settings: 'M4 7h16M4 17h16M8 4v6M16 14v6',
    bolt: 'm13 2-9 12h7l-1 8 10-12h-7Z',
    leaf: 'M20 3C6 2 1 9 6 16s17 1 14-13ZM4 21 15 10',
    refresh: 'M20 7v5h-5M4 17v-5h5M6 7a7 7 0 0 1 12-1l2 3M4 15l2 3a7 7 0 0 0 12-1',
    external: 'M14 3h7v7M21 3 10 14M10 3H3v18h18v-7',
  };
</script>
<svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d={paths[name] || paths.arrow} /></svg>
