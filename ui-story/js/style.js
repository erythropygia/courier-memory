/* Harita stili: LÖSEV haritasının yapısı (OpenMapTiles şeması, fill-extrusion binalar), bu projeye göre daha sakin palet.
   Kaynak önce yerel karolar (ui-story/tiles, z7–14); yoksa çevrimiçi OpenFreeMap. */
(function (CM) {
  const C = {
    land: '#EFE8DC', residential: '#EAE2D4', park: '#D5E3C2', wood: '#C9DCB4', sand: '#EFE2C2',
    water: '#A8D2E2', waterDeep: '#93C4D8', waterLabel: '#3D6E86',
    road: '#FFFFFF', roadCasing: '#E0D4C2', roadMajor: '#F8E3BC', roadMajorCasing: '#E2C48C',
    pedestrian: '#F7F1E7', rail: '#CDBFA9', building: '#E6DBCA', buildingTop: '#DCCDB6', label: '#6B6259',
  };
  CM.MAP_COLOR = C;
  // yerel karo kapsamı (tools: tiles_dl) — ana: z8–14, bağlam: z7–10 geniş
  CM.TILE_BORDER = [28.98, 41.0, 29.4, 41.28];
  CM.CONTEXT_BORDER = [28.5, 40.7, 30.0, 41.7];

  const name = ['coalesce', ['get', 'name:tr'], ['get', 'name']];
  const noteBT = ['match', ['get', 'brunnel'], ['bridge', 'tunnel'], false, true];
  const cls = (...c) => ['match', ['get', 'class'], c, true, false];
  const w = (...s) => ['interpolate', ['exponential', 1.4], ['zoom'], ...s];

  CM.style = function (local) {
    const base = new URL('.', location.href).href;
    const sources = {};
    if (local) {
      sources.omt = { type: 'vector', tiles: [base + 'tiles/{z}/{x}/{y}.pbf'], minzoom: 8, maxzoom: 14, bounds: CM.TILE_BORDER };
      sources.ctx = { type: 'vector', tiles: [base + 'tiles/{z}/{x}/{y}.pbf'], minzoom: 7, maxzoom: 10, bounds: CM.CONTEXT_BORDER };
    } else {
      sources.omt = { type: 'vector', url: 'https://tiles.openfreemap.org/planet' };
    }
    const ctx = local ? [
      { id: 'ctx-water', type: 'fill', source: 'ctx', 'source-layer': 'water', paint: { 'fill-color': C.waterDeep } },
      { id: 'ctx-wood', type: 'fill', source: 'ctx', 'source-layer': 'landcover', filter: cls('wood'), paint: { 'fill-color': C.wood } },
      { id: 'ctx-road', type: 'line', source: 'ctx', 'source-layer': 'transportation', filter: cls('motorway', 'trunk', 'primary'), paint: { 'line-color': C.roadMajorCasing, 'line-width': 1 } },
    ] : [];
    return {
      version: 8,
      glyphs: local ? base + 'fonts/{fontstack}/{range}.pbf' : 'https://tiles.openfreemap.org/fonts/{fontstack}/{range}.pbf',
      sources,
      layers: [
        { id: 'land', type: 'background', paint: { 'background-color': C.land } },
        ...ctx,
        { id: 'residential', type: 'fill', source: 'omt', 'source-layer': 'landuse', filter: cls('residential', 'suburb', 'neighbourhood'), paint: { 'fill-color': C.residential } },
        { id: 'park', type: 'fill', source: 'omt', 'source-layer': 'park', paint: { 'fill-color': C.park } },
        { id: 'grass', type: 'fill', source: 'omt', 'source-layer': 'landcover', filter: cls('grass', 'farmland'), paint: { 'fill-color': C.park } },
        { id: 'wood', type: 'fill', source: 'omt', 'source-layer': 'landcover', filter: cls('wood'), paint: { 'fill-color': C.wood } },
        { id: 'sand', type: 'fill', source: 'omt', 'source-layer': 'landcover', filter: cls('sand'), paint: { 'fill-color': C.sand } },
        { id: 'pitch', type: 'fill', source: 'omt', 'source-layer': 'landuse', filter: cls('pitch', 'stadium', 'school'), paint: { 'fill-color': '#E4E3C8' } },
        { id: 'water', type: 'fill', source: 'omt', 'source-layer': 'water', filter: ['!=', ['get', 'brunnel'], 'tunnel'],
          paint: { 'fill-color': ['interpolate', ['linear'], ['zoom'], 11, C.waterDeep, 16, C.water] } },
        { id: 'water-edge', type: 'line', source: 'omt', 'source-layer': 'water', paint: { 'line-color': '#86B8CD', 'line-width': w(12, 0.5, 18, 2.5) } },
        { id: 'pedestrian-area', type: 'fill', source: 'omt', 'source-layer': 'transportation', filter: ['match', ['geometry-type'], ['Polygon', 'MultiPolygon'], true, false], paint: { 'fill-color': C.pedestrian } },
        { id: 'road-minor-casing', type: 'line', source: 'omt', 'source-layer': 'transportation', minzoom: 14, filter: ['all', noteBT, cls('minor', 'service')], layout: { 'line-cap': 'round', 'line-join': 'round' }, paint: { 'line-color': C.roadCasing, 'line-width': w(14, 3, 18, 20) } },
        { id: 'road-major-casing', type: 'line', source: 'omt', 'source-layer': 'transportation', filter: ['all', noteBT, cls('secondary', 'tertiary', 'primary', 'trunk', 'motorway')], layout: { 'line-cap': 'round', 'line-join': 'round' }, paint: { 'line-color': C.roadMajorCasing, 'line-width': w(10, 0.8, 18, 28) } },
        { id: 'path', type: 'line', source: 'omt', 'source-layer': 'transportation', minzoom: 15, filter: ['all', ['match', ['geometry-type'], ['LineString', 'MultiLineString'], true, false], cls('path', 'pedestrian')], layout: { 'line-join': 'round', 'line-cap': 'round' }, paint: { 'line-color': '#FFFFFF', 'line-width': w(15, 1.5, 18, 6), 'line-opacity': 0.95 } },
        { id: 'road-minor', type: 'line', source: 'omt', 'source-layer': 'transportation', minzoom: 12.5, filter: ['all', noteBT, cls('minor', 'service')], layout: { 'line-cap': 'round', 'line-join': 'round' }, paint: { 'line-color': C.road, 'line-width': w(12.5, 0.4, 14, 2, 18, 16) } },
        { id: 'road-major', type: 'line', source: 'omt', 'source-layer': 'transportation', filter: ['all', noteBT, cls('secondary', 'tertiary', 'primary', 'trunk', 'motorway')], layout: { 'line-cap': 'round', 'line-join': 'round' }, paint: { 'line-color': C.roadMajor, 'line-width': w(10, 0.5, 18, 24) } },
        { id: 'bridge', type: 'line', source: 'omt', 'source-layer': 'transportation', filter: ['all', ['==', ['get', 'brunnel'], 'bridge'], cls('minor', 'secondary', 'tertiary', 'primary', 'trunk', 'motorway', 'pedestrian', 'path')], layout: { 'line-cap': 'round' }, paint: { 'line-color': C.road, 'line-width': w(12, 1.5, 18, 16) } },
        { id: 'rail', type: 'line', source: 'omt', 'source-layer': 'transportation', filter: ['all', noteBT, cls('rail', 'transit')], paint: { 'line-color': C.rail, 'line-width': w(13, 0.6, 18, 3) } },
        { id: 'ferry', type: 'line', source: 'omt', 'source-layer': 'transportation', filter: cls('ferry'), paint: { 'line-color': '#FFFFFF', 'line-width': 1.2, 'line-dasharray': [2, 3], 'line-opacity': 0.8 } },
        { id: 'building-flat', type: 'fill', source: 'omt', 'source-layer': 'building', minzoom: 13, maxzoom: 14.5, paint: { 'fill-color': C.building } },
        { id: 'building-3d', type: 'fill-extrusion', source: 'omt', 'source-layer': 'building', minzoom: 14.5,
          paint: {
            'fill-extrusion-color': ['interpolate', ['linear'], ['coalesce', ['get', 'render_height'], 8], 0, C.building, 40, C.buildingTop],
            'fill-extrusion-height': ['interpolate', ['linear'], ['zoom'], 14.5, 0, 15.2, ['coalesce', ['get', 'render_height'], 8]],
            'fill-extrusion-base': ['coalesce', ['get', 'render_min_height'], 0],
            'fill-extrusion-opacity': 0.92, 'fill-extrusion-vertical-gradient': true,
          } },
        { id: 'water-name', type: 'symbol', source: 'omt', 'source-layer': 'water_name',
          layout: { 'text-field': name, 'text-font': ['Noto Sans Italic'], 'text-size': 14, 'text-letter-spacing': 0.15, 'text-max-width': 6 },
          paint: { 'text-color': C.waterLabel, 'text-halo-color': 'rgba(255,255,255,0.5)', 'text-halo-width': 1.2 } },
        { id: 'street-name', type: 'symbol', source: 'omt', 'source-layer': 'transportation_name', minzoom: 15,
          layout: { 'symbol-placement': 'line', 'text-field': name, 'text-font': ['Noto Sans Regular'], 'text-size': ['interpolate', ['linear'], ['zoom'], 15, 11, 18, 14], 'text-rotation-alignment': 'map', 'text-pitch-alignment': 'viewport' },
          paint: { 'text-color': C.label, 'text-halo-color': C.land, 'text-halo-width': 1.4 } },
        { id: 'place-name', type: 'symbol', source: 'omt', 'source-layer': 'place', filter: ['any', cls('town', 'suburb'), ['all', cls('village', 'neighbourhood', 'quarter'), ['>=', ['zoom'], 13]]],
          layout: { 'text-field': name, 'text-font': ['Noto Sans Bold'], 'text-size': ['interpolate', ['linear'], ['zoom'], 10, 11, 16, 15], 'text-transform': 'uppercase', 'text-letter-spacing': 0.16, 'text-max-width': 8 },
          paint: { 'text-color': 'rgba(26,23,20,0.42)', 'text-halo-color': C.land, 'text-halo-width': 1.6 } },
      ],
    };
  };
})(window.CM);
