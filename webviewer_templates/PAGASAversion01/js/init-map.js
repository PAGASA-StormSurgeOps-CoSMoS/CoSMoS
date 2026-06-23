const layerOptions = {
  "detectRetina": false,
  "opacity": 0.7,
  "maxNativeZoom": 13,
  "maxZoom": 22,
  "minZoom": 0,
  "noWrap": false,
  "subdomains": "abc",
  "zIndex": 10,
  "tms": false
}

const cviColors = [
  '#00ff00',
  '#ffff00',
  '#ffa500',
  '#ff0000'
]


// Base layers
const tile_layer_osm = L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
  "attribution": "Data by \u0026copy; \u003ca href=\"https://openstreetmap.org\"\u003eOpenStreetMap\u003c/a\u003e, under \u003ca href=\"http://www.openstreetmap.org/copyright\"\u003eODbL\u003c/a\u003e.",
  "detectRetina": false,
  "maxNativeZoom": 19,
  "maxZoom": 19,
  "minZoom": 0,
  "noWrap": false,
  "opacity": 0.8,
  "subdomains": "abc",
  "tms": false
});
const Esri_WorldImagery = L.tileLayer(
  'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', {
    attribution: 'Tiles &copy; Esri &mdash; Source: Esri, i-cubed, USDA, USGS, AEX, GeoEye, Getmapping, Aerogrid, IGN, IGP, UPR-EGP, and the GIS User Community',
    "opacity": 0.8,
    "maxNativeZoom": 19,
    "maxZoom": 19,
    "minZoom": 0
  });

  const CartoDB = L.tileLayer(
    "https://cartodb-basemaps-{s}.global.ssl.fastly.net/rastertiles/voyager/{z}/{x}/{y}.png", {
      attribution: "&copy; <a href='http://www.openstreetmap.org/copyright'>OpenStreetMap</a> &copy; <a href='http://cartodb.com/attributions'>CartoDB</a>",
      detectRetina: false,
      maxNativeZoom: 19,
      maxZoom: 19,
      minZoom: 0,
      noWrap: false,
      subdomains: "abc",
      tms: false
    }
  )

// Map
const map = L.map("map", {
  center: [18.2, -66.5],
  crs: L.CRS.EPSG3857,
  zoom: 10,
  minZoom: 0,
  maxZoom: 19,
  zoomControl: true,
  preferCanvas: false,
  layers: [Esri_WorldImagery]
});
console.log('map')

//const controlLegend = L.control({
//  position: 'bottomright'
//});
//controlLegend.onAdd = function (map) {
//  const div = L.DomUtil.create('div', 'info legend')
//  div.innerHTML =
//  `
//  <span class="title"><b>Flood depth</b></span><br>
//  <i style="background:#CCFFFF"></i><span> 0.0&nbsp-&nbsp;0.33&#8201;m</span><br>
//  <i style="background:#40E0D0"></i><span> 0.33&nbsp;-&nbsp;1.0&#8201;m</span><br>
//  <i style="background:#00BFFF"></i><span> 1.0&nbsp-&nbsp;2.0&#8201;m</span><br>
//  <i style="background:#0909FF"></i><span>&gt;2.0&#8201;m</span><br>
//  `
//  return div;
//};

//const runupLegend = L.control({
//  position: 'bottomright'
//});
//runupLegend.onAdd = function (map) {
//  const div = L.DomUtil.create('div', 'info legend')
//  div.innerHTML =
//  `
//  <span class="title"><b>TWL</b></span><br>
//  <i style="background:#00ff00"></i><span> 0.0&nbsp-&nbsp;1.0&#8201;m</span><br>
//  <i style="background:#ffff00"></i><span> 1.0&nbsp;-&nbsp;2.0&#8201;m</span><br>
//  <i style="background:#ffa500"></i><span> 2.0&nbsp-&nbsp;4.0&#8201;m</span><br>
//  <i style="background:#ff0000"></i><span>&gt;4.0&#8201;m</span><br>
//  `
//  return div;
//};

const cviLegend = L.control( {
  position: 'topright'
});
cviLegend.onAdd = function (map) {
const div = L.DomUtil.create('div', 'info legend')
div.innerHTML =

`
<span class="title"><b>Vulnerability</b></span><br>

<svg xmlns="http://www.w3.org/2000/svg" width="20" height="10">
  <g transform="translate(0, 5)">
    <line x1="0" x2="20" y1="0" y2="0"
      style="stroke: #00ff00; stroke-width: 3px;"></line>
  </g>
</svg>
<span> Low</span><br>

<svg xmlns="http://www.w3.org/2000/svg" width="20" height="10">
  <g transform="translate(0, 5)">
    <line x1="0" x2="20" y1="0" y2="0"
      style="stroke: #ffff00; stroke-width: 3px;"></line>
  </g>
</svg>
<span> Moderate</span><br>

<svg xmlns="http://www.w3.org/2000/svg" width="20" height="10">
  <g transform="translate(0, 5)">
    <line x1="0" x2="20" y1="0" y2="0"
      style="stroke: #ffa500; stroke-width: 3px;"></line>
  </g>
</svg>
<span> High</span><br>

<svg xmlns="http://www.w3.org/2000/svg" width="20" height="10">
  <g transform="translate(0, 5)">
    <line x1="0" x2="20" y1="0" y2="0"
      style="stroke: #ff0000; stroke-width: 3px;"></line>
  </g>
</svg>
<span> Very High</span><br>

</div>
`
  return div;
};

const controlScale = L.control.scale({
  imperial: false,
  position: 'bottomright'
}).addTo(map);
// L.control.betterscale().addTo(map);
// Layer control
const baseMaps = {
  "OpenStreetMap": tile_layer_osm,
  "CartoDB": CartoDB,
  "Esri WorldImagery": Esri_WorldImagery
};

//const activeVariables = {
//  "TWL": true,
//  "SWL": true,
//  "FM": true,
//  "FE": false,
//  "COAST": false,
//  "OVERTOPPING": false,
//  "COASTLINE_CVI": false,
//  "OVERTOPPING_CVI": false,
//  "OVERALL_CVI": false,
//};

// Default layer
//let currentScenarioId = 'SC01'
//let currentReturnPeriod = 'BT'

//let dataLayerFor = function(dataId, returnPeriod) {
//  const key = `${dataId}_${returnPeriod}`
//  console.log(key);
//  return dataLayers[key];
//}

//let changeBasemap = function(element) {
//  const layerId = element.getAttribute("value");
//  map.removeLayer(currentLayer);
//  currentLayer = baseMaps[layerId];
//  map.addLayer(currentLayer);
//}

//let setDefaultLayers = function() {
//  for (const variableId in activeVariables ) {
//    if (activeVariables[variableId]) {
//      const newLayer = layerFor(currentScenarioId, currentReturnPeriod, variableId);
//      map.addLayer(newLayer);
//      if (variableId === 'FM') controlLegend.addTo(map)
//	  if (variableId === 'TWL') runupLegend.addTo(map)
//      if (variableId.startsWith('CVI_')) cviLegend.addTo(map)
//    }
//  }
//}

//let changeScenario = function(element) {
//  const scenarioId = element.getAttribute("value");
//  for (const variableId in activeVariables ) {
//    if (activeVariables[variableId]) {
//      const oldLayer = layerFor(currentScenarioId, currentReturnPeriod, variableId);
//      map.removeLayer(oldLayer);
//      const newLayer = layerFor(scenarioId, currentReturnPeriod, variableId);
//      map.addLayer(newLayer);
//    }
//  }
//  currentScenarioId = scenarioId;
//}

//let changeReturnPeriod = function(element) {
//  const returnPeriod = element.getAttribute("value");
//  for (const variableId in activeVariables ) {
//    if (activeVariables[variableId]) {
//      const oldLayer = layerFor(currentScenarioId, currentReturnPeriod, variableId);
//      map.removeLayer(oldLayer);
//      const newLayer = layerFor(currentScenarioId, returnPeriod, variableId);
//      map.addLayer(newLayer);
//    }
//  }
//  currentReturnPeriod = returnPeriod;
//}

//let changeVariable = function(element) {
//  const variableId = element.value;
//  const active = element.checked;
//  activeVariables[variableId] = active;
//  const activeCVIlayers = Object.entries(activeVariables).filter( ([key,entry]) => {
//    return key.endsWith('_CVI') && entry })
//  const layer = layerFor(currentScenarioId, currentReturnPeriod, variableId);
//  if (active) {
//    map.addLayer(layer);
//    if (variableId === 'FM') controlLegend.addTo(map)
//	if (variableId === 'TWL') runupLegend.addTo(map)
//    if (variableId.endsWith('_CVI') && activeCVIlayers.length === 1) {
//      cviLegend.addTo(map)
//    }
//  } else {
//    map.removeLayer(layer);
//    if (variableId === 'FM') controlLegend.remove()
//	if (variableId === 'TWL') runupLegend.remove()
//    if (variableId.endsWith('_CVI') && activeCVIlayers.length === 0) cviLegend.remove()
//  }
//}


var overlayMaps = {};
L.control.layers(baseMaps, overlayMaps).addTo(map);
