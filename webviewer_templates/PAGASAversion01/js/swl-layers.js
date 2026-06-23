// SWL layers
const pointToLayerSWL = function (feature, latlng) {
  return new L.CircleMarker(latlng, {
    radius: 3,
    fillOpacity: 0.25,
	opacity: 0,
    color: 'blue'
  });
};

const onEachFeatureSWL50 = function (feature, layer) {
  const html = 'Location nr: &#9;' + feature.properties.LocNr + '<br />' +
    'Latitude: &#9;' + feature.properties.Lat + ' [dgr N] &#9;' + '<br />' +
    'Longitude: &#9;' + feature.properties.Lon + ' [dgr E] &#9;' + '<br />' +
    'Significant wave height: &#9;' + feature.properties.Hs + ' [m] &#9;' +
    '<br />' +
	'Peak wave period: &#9;' + feature.properties.Tp + ' [m] &#9;' +
    '<br />' +
    'Still Water Level: &#9;' + feature.properties.WL +
    ' [m above MSL] &#9;' + '<br />'
  layer.bindTooltip(L.tooltip({ direction: 'top' }).setContent(html));
  layer.bindPopup(html);
};

const onEachFeatureSWL100 = function (feature, layer) {
  const html = 'Location nr: &#9;' + feature.properties.LocNr + '<br />' +
    'Latitude: &#9;' + feature.properties.Lat + ' [dgr N] &#9;' + '<br />' +
    'Longitude: &#9;' + feature.properties.Lon + ' [dgr E] &#9;' + '<br />' +
    'Significant wave height: &#9;' + feature.properties.Hs + ' [m] &#9;' +
    '<br />' +
	'Peak wave period: &#9;' + feature.properties.Tp + ' [m] &#9;' +
    '<br />' +
    'Still Water Level: &#9;' + feature.properties.WL +
    ' [m above MSL] &#9;' + '<br />'
  layer.bindTooltip(L.tooltip({ direction: 'top' }).setContent(html));
  layer.bindPopup(html);
};


const pt_SC01_BT_SWL = L.geoJson(undefined, {
  pointToLayer: pointToLayerSWL,
  onEachFeature: onEachFeatureSWL50
})
layers["SC01_BT_SWL"] = pt_SC01_BT_SWL;
