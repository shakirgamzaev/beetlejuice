// Image-space coordinates traced against the user's complete 1773 × 1407 Lot 9 overview.
// These are NOT latitude/longitude. IDs and obscured boundaries require onsite review.
export const LOT_NAME = 'FIU Parking Lot 9';
export const restrictionLabels = {
  unverified: 'Permit type unverified',
  staff: 'Faculty / staff',
  accessible: 'Accessible parking',
  metered: 'Metered · $1.50/hr · $8/day',
  admin: 'Admin decal'
};
export const lotBoundary = 'M115 1380 C34 1180 14 1020 44 790 C52 570 230 310 447 184 C650 45 874 0 1040 24 C1190 13 1410 84 1575 148 Q1705 155 1720 250 L1743 764 Q1750 810 1680 822 L1390 866 Q991 965 576 1206 L329 1370 Z';
export const islands = [
  'M177 1248 L235 1250 L235 1295 L184 1293 Z',
  'M177 1108 Q234 1100 234 1130 L234 1143 L174 1143 Z',
  'M177 974 Q231 966 234 986 L234 1005 L170 1005 Z',
  'M315 683 L395 683 Q436 699 396 718 L318 718 Q289 704 315 683 Z',
  'M309 988 L401 988 Q433 1002 405 1020 L307 1020 Z',
  'M499 274 L500 226 L552 193 L611 175 L613 225 L557 230 L557 280 Z',
  'M500 528 L590 528 Q628 544 590 561 L502 561 Z',
  'M500 817 L596 817 Q628 833 595 849 L496 849 Z',
  'M690 168 L689 134 L747 110 L805 94 L805 148 L749 149 L749 174 Z',
  'M690 441 L788 441 Q821 457 787 472 L690 472 Z',
  'M690 739 L788 739 Q821 757 788 774 L690 774 Z',
  'M690 1073 L749 1073 L806 1039 L806 1074 L685 1113 Z',
  'M880 83 L997 83 L1002 115 L879 115 Z',
  'M878 392 L974 392 Q1014 410 977 426 L879 426 Z',
  'M879 661 L979 661 Q1010 679 978 697 L879 697 Z',
  'M879 937 L939 937 L994 908 L994 946 L877 985 Z',
  'M1076 102 L1123 99 L1190 118 L1190 151 L1130 151 L1128 123 L1075 124 Z',
  'M1078 361 L1170 361 Q1205 380 1170 396 L1078 396 Z',
  'M1078 604 L1175 604 Q1205 621 1175 640 L1078 640 Z',
  'M1075 843 L1130 843 L1190 823 L1190 851 L1070 887 Z',
  'M1260 145 L1318 164 L1377 184 L1377 211 L1318 206 L1318 180 L1260 180 Z',
  'M1260 391 L1355 391 Q1390 408 1355 425 L1260 425 Z',
  'M1260 580 L1359 580 Q1390 599 1357 615 L1260 615 Z',
  'M1260 769 L1320 769 L1377 749 L1377 781 L1256 821 Z',
  'M1458 199 L1518 209 L1580 230 L1580 259 L1520 256 L1520 241 L1458 230 Z',
  'M1457 418 L1558 418 Q1591 435 1558 451 L1457 451 Z',
  'M1457 560 L1559 560 Q1593 578 1558 592 L1457 592 Z',
  'M1457 754 L1555 754 Q1589 771 1557 792 L1457 792 Z',
  'M1640 248 Q1694 261 1694 288 L1637 288 Q1609 269 1640 248 Z',
  'M1630 510 L1692 510 L1692 554 L1629 554 Z',
  'M1631 746 L1691 746 Q1699 782 1667 789 L1630 789 Z',
];

// Segments stop at the islands; no continuous grid is laid across them.
const rows = [
  ['A', 177, [[670,6],[856,5],[1012,3],[1150,4]], 'unverified'],
  ['B', 306, [[510,6],[724,10],[1027,10]], 'unverified'],
  ['C', 369, [[402,10],[724,10],[1027,10]], 'unverified'],
  ['D', 499, [[292,9],[567,9],[855,12]], 'unverified'],
  ['E', 562, [[234,11],[567,9],[855,12]], 'unverified'],
  ['F', 689, [[179,10],[480,9],[783,11]], 'unverified'],
  ['G', 752, [[153,11],[480,9],[783,9]], 'staff'],
  ['H', 878, [[124,10],[432,8],[705,9]], 'staff'],
  ['I', 942, [[124,10],[432,8],[705,8]], 'staff'],
  ['J', 1076, [[158,7],[402,7],[647,7]], 'staff'],
  ['K', 1139, [[158,7],[402,7],[647,6]], 'staff'],
  ['L', 1259, [[214,6],[431,5],[622,5]], 'staff'],
  ['M', 1322, [[219,6],[431,5],[622,5]], 'unverified'],
  ['N', 1457, [[250,6],[457,4],[600,5]], 'admin'],
  ['O', 1520, [[266,5],[457,4],[600,5]], 'admin'],
];
export const lotSpots = [];
for (const [row, x, segments, restriction] of rows) {
  let number = 1;
  for (const [top, count] of segments) {
    for (let i = 0; i < count; i++) {
      lotSpots.push({ spot_id: `${row}${number++}`, row, x, y: top + i * 25.9, width: 56, height: 23,
        angle: 0, restriction, parallel: false, latitude: null, longitude: null,
        review: i === 0 || i === count - 1 ? 'Check boundary near landscaping against the site.' : 'Image-derived stall; not yet field verified.' });
    }
  }
}
// East edge: five wheelchair-marked stalls separated by three access aisles.
for (const [i,y] of [292,348,376,432,460].entries()) {
  lotSpots.push({spot_id:`Q${i+1}`,row:'Q',x:1631,y,width:57,height:25,angle:0,restriction:'accessible',parallel:false,latitude:null,longitude:null,review:'Wheelchair marking visible in supplied reference; verify current signage.'});
}
for (let i=0;i<7;i++) lotSpots.push({spot_id:`Q${i+6}`,row:'Q',x:1631,y:562+i*25.9,width:57,height:23,angle:0,restriction:'metered',parallel:false,latitude:null,longitude:null,review:'Metered space; rate currently set to $1.50/hour and $8/day pending confirmation.'});
export const exclusions = [
  {x:1631,y:322,width:57,height:20}, {x:1631,y:405,width:57,height:20},
  // The southern access aisle ends before the landscaped island.
  {x:1631,y:490,width:57,height:13},
];
// Parallel bays follow individually sampled sections of the curved outer curb.
// Start at the northern entrance and number counterclockwise toward the southwest.
const perimeter = [[1421,126],[1364,106],[1306,88],[1247,70],[1188,54],[1127,43],[1066,37],[1005,35],[944,39],[883,48],[823,62],[764,81],[705,103],[648,129],[594,157],[542,188],[492,222],[446,258],[402,297],[361,339],[322,385],[285,434],[250,486],[219,540],[192,595],[168,652],[148,710],[115,769],[96,830],[81,892],[75,954],[80,1016],[90,1077],[101,1137],[114,1197],[130,1255],[148,1312]];
perimeter.forEach(([x,y],i)=>{
  const next=perimeter[Math.min(i+1,perimeter.length-1)], previous=perimeter[Math.max(0,i-1)];
  let angle=Math.atan2(next[1]-previous[1],next[0]-previous[0])*180/Math.PI;
  if(angle>90)angle-=180;
  if(angle<-90)angle+=180;
  // Pull each bay slightly inward from the curb so the stall body stays clear of landscaping.
  const dx=886-x, dy=704-y, length=Math.hypot(dx,dy)||1;
  const inwardX=x+dx/length*12, inwardY=y+dy/length*12;
  lotSpots.push({spot_id:`P${String(i+1).padStart(2,'0')}`,row:'P',x:inwardX-23,y:inwardY-10,width:46,height:20,angle,restriction:'unverified',parallel:true,latitude:null,longitude:null,review:'Perimeter parallel bay; spacing and endpoints require field verification.'});
});
export function mappedObservations(observations, now, online, statusOf) {
  const index = new Map(observations.map(s => [s.spot_id, s]));
  return lotSpots.map(layout => {
    const observation = index.get(layout.spot_id);
    // Old A-1 demo labels must not be silently assigned to a real physical stall.
    return { ...layout, ...observation, status: observation ? statusOf(observation, now, online) : 'unmonitored' };
  });
}
