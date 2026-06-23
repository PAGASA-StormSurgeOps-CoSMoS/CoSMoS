//var wind_color_scale = ["rgb(0,0,128)","rgb(0,0,178)","rgb(0,0,229)","rgb(0,25,255)","rgb(0,76,255)","rgb(0,127,255)","rgb(0,178,255)","rgb(0,229,255)","rgb(25,255,229)","rgb(76,255,178)","rgb(127,255,127)","rgb(178,255,76)","rgb(229,255,25)","rgb(255,229,0)","rgb(255,178,0)","rgb(255,127,0)","rgb(255,76,0)","rgb(255,25,0)","rgb(255,51,51)","rgb(255,153,153)","rgb(255,255,255)"];
var wind_color_scale = ["rgb(0,255,255)","rgb(61,255,195)","rgb(122,255,134)","rgb(182,255,73)","rgb(243,255,12)","rgb(255,239,0)","rgb(255,219,0)","rgb(255,199,0)","rgb(255,178,0)","rgb(255,158,0)","rgb(255,138,0)","rgb(255,116,12)","rgb(255,91,37)","rgb(255,67,61)","rgb(255,43,85)","rgb(255,18,110)","rgb(248,0,127)","rgb(218,0,121)","rgb(189,0,116)","rgb(159,0,111)","rgb(130,0,105)","rgb(100,0,100)"];

function makeWindLayer() {
  var pth = "data/" + currentScenario["name"] + "/" + currentCycle + "/"
  loadjs(pth + "wind.json.js", windLoaded, windFailed);
};

function windLoaded() {
  // Add data

  var velocityLayer = L.velocityLayer({
		displayValues: true,
		displayOptions: {
			velocityType: 'Global Wind',
			displayPosition: 'bottomleft',
			displayEmptyString: 'No wind data'
		},
        data: wind,
		maxVelocity: max_wind_velocity,
		velocityScale: 0.01,
		colorScale: wind_color_scale
  });
  layers["wind"].push(velocityLayer);
  document.getElementById('variable_wind').disabled = false
  if (currentVariable["name"] == "wind") {
      currentLayer = layers[currentVariable["name"]][0];
      map.addLayer(velocityLayer);
      removeOldLayer();
  }
}

function windFailed() {
	console.log('Could not load wind.js');
}
