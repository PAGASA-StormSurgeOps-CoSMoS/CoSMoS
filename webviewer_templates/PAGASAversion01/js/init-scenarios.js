var currentScenario
var currentVariable
var currentCycle
var currentLayer
var controlLegend
var iconLegend
var currentTime = 0
var previousTime = -1
var stations
var buoys
var model_outlines
var xb_markers
var cyclone_track
var cyclone_track_ensemble
var animationTimeout
var wind
var max_wind_velocity

function loadjs(file_name, callback, failed) {

  let myScript = document.createElement("script");
  myScript.setAttribute("src", file_name);
  myScript.addEventListener("load", callback, false);
  myScript.addEventListener("error", failed, false);
  document.body.appendChild(myScript);
  console.log('request sent');
}

// Read in scenarios
loadjs("data/scenarios.js", scenariosLoaded, scenarioLoadError);

function scenarioLoadError() {
	console.log('Error! Could not load data/scenarios.js !');
}

function variableLoadError() {
	console.log('Error! Could not load variables !');
}

function stationsLoadError() {
	console.log('Error! Could not load stations !');
	stations = null;
	addStations();
}

function buoysLoadError() {
	console.log('Error! Could not load wave buoys !');
	buoys = null;
	addBuoys();
}

function modelOutlinesLoadError() {
	console.log('Error! Could not load wave buoys !');
	model_outline_data = null;
	addModelOutlines();
}

function xbeachLoadError() {
	console.log('Error! Could not load XBeach markers !');
	xb_markers = null;
	addXBeachMarkers();
}

function cycloneTrackLoadError() {
	console.log('Error! Could not load cyclone track !');
	track_data = null;
	addCycloneTrack();
}

function cycloneTrackEnsembleLoadError() {
	console.log('Error! Could not load cyclone track ensemble!');
	track_ensemble_data = null;
	addCycloneTrackEnsemble();
}

function scenariosLoaded() {

  console.log(scenario.length.toString() + " scenarios found !");

  currentScenario = scenario[0]
  currentCycle = currentScenario["cycle_string"]
  console.log("Active scenario is " + currentScenario["name"]);

  var fieldset    = document.getElementById('scenarios');

  // Clear existing fieldset (legend + listbox)
  while (fieldset.hasChildNodes()) {
    fieldset.removeChild(fieldset.firstChild);
  }

  // Add legend
  var newLegend = document.createElement('legend');
  newLegend.innerHTML = "Storm Scenario";
  fieldset.appendChild(newLegend);

  // Listbox
  newSelect = document.createElement('select');
  newSelect.addEventListener("change", function(){changeScenario(this);});
  for (let i = 0; i < scenario.length; i++) {
      var newOption = document.createElement('option');
      var newInput = document.createElement('input');
      newInput.type       = "radio";
      newInput.id         = "";
      newInput.name       = "optionsLayer";
      newOption.value     = scenario[i].name;
      newOption.innerHTML = scenario[i].long_name;
      newSelect.appendChild(newOption);
  }

  fieldset.appendChild(newSelect);

  selectScenario();
  clearTimeout(animationTimeout);

}

function selectScenario() {


  document.getElementById("description_text").innerHTML = currentScenario["description"]

  // Set new zoom
  map.setView([currentScenario["lat"], currentScenario["lon"]], currentScenario["zoom"]);

  // Listbox
  var fieldset    = document.getElementById('scenarios');

  // Remove cycle pop-up menu
  var selector = document.getElementById('cycle_selector');
  if (selector) {
    selector.remove();
  }
  
  if (currentScenario["previous_cycles"]) {
    var cycleSelect = document.createElement('select');
    cycleSelect.id = 'cycle_selector';
    cycleSelect.addEventListener("change", function(){changeCycle(this);});
    for (let i = 0; i < currentScenario["previous_cycles"].length; i++) {
        var newOption = document.createElement('option');
        var newInput = document.createElement('input');
        newInput.type       = "radio";
        newInput.id         = "";
        newInput.name       = "optionsLayer";
        newOption.value     = currentScenario["previous_cycles"][i];
        newOption.innerHTML = currentScenario["previous_cycles"][i];
        cycleSelect.appendChild(newOption);
    }
    fieldset.appendChild(cycleSelect);
  }
  currentCycle = currentScenario["cycle_string"]

  selectCycle(); 

}

function selectCycle() {

  makeIconLegend();

  var fieldset    = document.getElementById('scenarios');
  

  // Read map variables
  var pth = "data/" + currentScenario["name"] + "/" + currentCycle + "/"
  loadjs(pth + "variables.js", variablesLoaded, variableLoadError);
  console.log(pth + "variables.js")
  // Add tide stations
  loadjs(pth + "stations.geojson.js", addStations, stationsLoadError);
  // Add wave buoys
  loadjs(pth + "wavebuoys.geojson.js", addBuoys, buoysLoadError);
  // Add XBeach markers
  loadjs(pth + "xbeach.geojson.js", addXBeachMarkers, xbeachLoadError);
  // Add cyclone track
  loadjs(pth + "track.geojson.js", addCycloneTrack, cycloneTrackLoadError);
  // Add cyclone track ensemble
  loadjs(pth + "track_ensemble.geojson.js", addCycloneTrackEnsemble, cycloneTrackEnsembleLoadError);
  // Add model outlines
  loadjs(pth + "xb.geojson.js", addModelOutlines, modelOutlinesLoadError);


  var update_string = "Updated : " + currentScenario["last_update"]
  if (currentCycle) {
    update_string += "&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;CoSMoS : " + currentCycle
  }	
  if (currentScenario["meteo_string"]) {
    update_string += "&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;meteo : " + currentScenario["meteo_string"]
  }
  document.getElementById("status_text").innerHTML = update_string


}

function selectMode() {

//        <fieldset>
//          <legend>Storm Track</legend>
//          <div class="pure-g">
//            <label class="pure-u-2-5">
//              <input type="radio"  name="mode_option" value="best_track" checked onchange="changeMode(this)"/> Best track
//            </label>
//            <label class="pure-u-2-5">
//              <input type="radio"  name="mode_option" value="ensemble" onchange="changeMode(this)"/> Ensemble
//            </label>
//          </div>
//        </fieldset>


	console.log('Selected ' + currentMode);
}

function variablesLoaded() {

  console.log("Finished reading the variables in scenario " + currentScenario["long_name"]);
  currentScenario["variable"] = map_variables

  // Make map layers

  layers = {};
  var pth = "data/" + currentScenario["name"] + "/" + currentCycle + "/"

  for (let i = 0; i < currentScenario["variable"].length; i++) {

	var variable_format = currentScenario["variable"][i].format
	var variable_name   = currentScenario["variable"][i].name

	if (currentScenario["variable"][i].times !== undefined) {
	  var times         = currentScenario["variable"][i].times
	  var ntimes        = times.length
    }
    else {
		var ntimes = 0
    }

    currentScenario["variable"][i].ntimes = ntimes

    console.log("Making map layer : " + currentScenario["variable"][i].long_name);

    layers[variable_name] = new Array()

    if (variable_format == "xyz_tile_layer") {

        var maxNativeZoom = 16;
        if (currentScenario["variable"][i].max_native_zoom) {
			maxNativeZoom = currentScenario["variable"][i].max_native_zoom;
        }

        var layerOpts = {
          "detectRetina": false,
          "opacity": 0.7,
          "maxNativeZoom": maxNativeZoom,
          "maxZoom": 22,
          "minZoom": 0,
          "noWrap": false,
          "subdomains": "abc",
          "zIndex": 10,
          "tms": false
        }

		if (ntimes>0) {
            for (let j = 0; j < ntimes; j++) {
        		time_string = times[j]["name"]
                this_layer = L.tileLayer(pth + variable_name + "/" + time_string + "/{z}/{x}/{y}.png", layerOpts);
                layers[variable_name].push(this_layer);
            }
        }

        else {
            this_layer = L.tileLayer(pth + variable_name + "/{z}/{x}/{y}.png", layerOpts);
            layers[variable_name].push(this_layer);
        }

    }

    else if (variable_format == "geojson") {

		// Quite a few different options for geojson layers

		if (variable_name == 'extreme_runup_height') {
			makeExtremeRunupLayer();
	    }
	    else if (variable_name == 'extreme_sea_level_and_wave_height') {
			makeExtremeSWLLayer();
     	}
		else if (variable_name == 'extreme_horizontal_runup_height') {
            makeExtremeRunupLayer_H();
        }
		else if (variable_name == 'extreme_runup_height_prc95') {
            makeExtremeRunupLayer_prob();
        }
		else if (variable_name == 'track_ensemble') {
            makeTrackEnsemble();
        }
		else if (variable_name == 'sallenger') {
			makeSallenger();
	    }
    else if (variable_name == 'erosion_regimes') {
      makeErosionRegimes();
        }
    }

    else if (variable_format == "vector_field") {

		// Quite a few different options for geojson layers

		if (variable_name == 'wind') {
			max_wind_velocity = currentScenario["variable"][i].max
			makeWindLayer();
	    }
    }
  }

  currentVariable = currentScenario["variable"][0]

  var fieldset= document.getElementById('variables');

  // Clear existing fieldset (legend + variables)
  while (fieldset.hasChildNodes()) {
    fieldset.removeChild(fieldset.firstChild);
  }

  var newLegend = document.createElement('legend');
  newLegend.innerHTML = "Map layers";
  fieldset.appendChild(newLegend);

  for (let i = 0; i < currentScenario["variable"].length; i++) {

      var newLabel = document.createElement('label');

      var newInput = document.createElement('input');
      newInput.type      = "radio";
      newInput.id        = "variable_" + currentScenario["variable"][i].name;
      newInput.name      = "optionsLayer";
      newInput.value     = currentScenario["variable"][i].name;
      newInput.addEventListener("change", function(){changeVariable(this);});
      if (i==0) {newInput.checked = true}

      newLabel.htmlFor = currentScenario["variable"][i].name;
      newLabel.setAttribute("class", "pure-radio");
      newLabel.appendChild(newInput);
      var newText = document.createTextNode(" " + currentScenario["variable"][i].long_name);
      newLabel.appendChild(newText);

      fieldset.appendChild(newLabel);

      if (currentScenario["variable"][i].name == "wind") {
        newInput.disabled = true
      }
//      document.getElementById('wind_time_string').innerHTML

  }

  selectVariable();

}

function variableLoadError() {
	console.log('Could not load variables.js!')
}

function selectVariable() {

  clearTimeout(animationTimeout);
  setTimes();

  // Remove old layer and legend
  if (currentLayer) {
    currentLayer.remove();
  }
  if (controlLegend) {
    controlLegend.remove();
  }

  // Add legend
  if (currentVariable["legend"]["contours"]) {
    // Add legend
    controlLegend = L.control({
      position: 'bottomright'
    });
    controlLegend.onAdd = function (map) {
      const div = L.DomUtil.create('div', 'info legend');
      var newSpan = document.createElement('span');
      newSpan.class = 'title';
      newSpan.innerHTML = '<b>' + currentVariable["legend"]["text"] + '</b>';
      div.appendChild(newSpan);
      div.appendChild(document.createElement("br"));
      for (let i = 0; i < currentVariable["legend"]["contours"].length; i++) {
        var newI = document.createElement('i');
        newI.setAttribute('style','background:' + currentVariable["legend"]["contours"][i].color);
        div.appendChild(newI);
        var newSpan = document.createElement('span');
        newSpan.innerHTML = currentVariable["legend"]["contours"][i].text;
        div.appendChild(newSpan);
        div.appendChild(document.createElement("br"));
      }
      var timetext = document.createElement('span');
      if (currentVariable["name"] == "wind") {
        timetext.id        = "wind_time_string"
        timetext.innerHTML = ""
        div.appendChild(timetext);
      }
      return div;
    };
    controlLegend.addTo(map);
  }

  // Add infographic
  if (currentVariable["infographic"]) {
      var iframe = parent.document.getElementById('myIframe');
      if (iframe) {
        iframe.src = 'img/infographics/' + currentVariable["infographic"] + '.html';
      }
  }

  selectTime();
}


function setTimes() {

  currentTime = 0;
  previousTime = -1;

  var fieldset = document.getElementById('times');
  // Clear existing fieldset (legend + listbox)
  while (fieldset.hasChildNodes()) {
    fieldset.removeChild(fieldset.firstChild);
  }

  if (currentVariable.ntimes>0) {
    // Add legend
    var newLegend = document.createElement('legend');
    newLegend.innerHTML = "Times";
    fieldset.appendChild(newLegend);
    // Listbox
    newSelect = document.createElement('select');
    newSelect.className = 'timeselector';
    newSelect.setAttribute('id','timeselector');
    newSelect.addEventListener("change", function(){changeTime(this);});
    for (let i = 0; i < currentVariable.times.length; i++) {
      if (currentVariable.times[i]["string"]) {
        var tstr = currentVariable.times[i]["string"]
      }
  	  else {
        var tstr = currentVariable.times[i]["name"]
      }
      var newOption = document.createElement('option');
      newOption.value     = i;
      newOption.innerHTML = tstr;
      newSelect.appendChild(newOption);
    }
    fieldset.appendChild(newSelect);

    var newPlay = document.createElement('button');
    newPlay.innerHTML = '<i class="fa fa-play"></i>';
    newPlay.style.marginLeft = "5px";
    newPlay.style.padding = "5px 5px 5px 5px";
    fieldset.appendChild(newPlay);
    newPlay.onclick = function () {
      nextFrame();
    };

    var newPause = document.createElement('button');
    newPause.innerHTML = '<i class="fa fa-pause"></i>';
    newPause.style.padding = "5px 5px 5px 5px";
    fieldset.appendChild(newPause);
    newPause.onclick = function () {
      clearTimeout(animationTimeout);
    };

  }
}

function selectTime() {
  // Set new currentLayer
  currentLayer = layers[currentVariable["name"]][currentTime];

  if (currentVariable["name"] == "wind") {

    // Add layer
    if (currentLayer) {
      map.addLayer(currentLayer);
      // Remove old layer after 0.2 s
      removeOldLayer();
    }

  }

  else {

    // Add layer
    if (currentLayer) {
      map.addLayer(currentLayer);
      // Remove old layer after 0.2 s
      currentLayer.onAdd(setTimeout(removeOldLayer, 200));
    }

  }
}

function removeOldLayer() {
  if (previousTime>-1) {
    console.log(previousTime)
    if (layers[currentVariable["name"]][previousTime]) {
      map.removeLayer(layers[currentVariable["name"]][previousTime]);
    }
  }
  previousTime = currentTime;
}

function nextFrame() {
	currentTime += 1;
    if (currentTime + 1 > currentVariable.ntimes) {
		currentTime = 1;
    }
    selectTime();
	document.getElementById('timeselector').value=currentTime;
	animationTimeout = setTimeout(nextFrame, 500);
}


// Called when scenario is selected from web gui
let changeScenario = function(element) {
  var name = element.value;
  currentScenario = scenario.find(x => x.name === name);
  selectScenario();
}

// Called when scenario is selected from web gui
let changeCycle = function(element) {
  var name = element.value;
  currentCycle = name;
  selectCycle();
}

// Called when best track of ensemble is selected from web gui
let changeMode = function(element) {
  var name = element.getAttribute("value");
  currentMode = element.getAttribute("value");
  selectMode();
}

// Called when scenario is selected from web gui
let changeVariable = function(element) {
  var name = element.getAttribute("value");
  currentVariable = currentScenario["variable"].find(x => x.name === name);
  selectVariable();
}

// Called when scenario is selected from web gui
let changeTime = function(element) {
  var name = element.value;
  currentTime = element.value;
  selectTime();
}

function makeIconLegend() {
  if (iconLegend) {
    iconLegend.remove();
  }
  // Add legend
  iconLegend = L.control({
    position: 'topleft'
  });
  iconLegend.onAdd = function (map) {
    const div = L.DomUtil.create('div', 'info legend');
    div.innerHTML += "<input type='checkbox' id='check_tide_gauge'>  <img src=./img/markers/tide_gauge.png height='25' width='25' style='margin:-1px 0px'> Tide gauge" + '<br>';
    div.innerHTML += "<input type='checkbox' id='check_wave_buoy'>  <img src=./img/markers/wave_buoy.png height='25' width='25' style='margin:-1px 0px'> Wave buoy" + '<br>';
//    div.innerHTML += "<input type='checkbox' id='check_erosion'>  <img src=./img/markers/erosion_marker_rw.png height='25' width='25' style='margin:-1px 0px'> Erosion" + '<br>';
    div.innerHTML += "<input type='checkbox' id='check_track'>  <img src=./img/markers/Category_3_hurricane_icon_c2.png height='36' width='18' style='margin:0px 0px -10px 0px'> Storm track" + '<br>';
    div.innerHTML += "<input type='checkbox' id='check_track_ensemble'> Track Ensemble" + '<br>';
//    div.innerHTML += "<input type='checkbox' id='check_model_outlines'> Models" + '<br>';
    return div;
  };
  iconLegend.addTo(map);
  var chk = document.getElementById('check_tide_gauge');
  chk.checked = true;
  chk.addEventListener('change', (event) => {
    if (event.currentTarget.checked) {
		addStations();
    } else {
		tide_gauges.remove();
    }
  })
  var chk = document.getElementById('check_wave_buoy');
  chk.checked = true;
  chk.addEventListener('change', (event) => {
    if (event.currentTarget.checked) {
		addBuoys();
    } else {
		wave_buoys.remove();
    }
  })

  var chk = document.getElementById('check_erosion');
  if (chk) {
    chk.checked = true;
    chk.addEventListener('change', (event) => {
      if (event.currentTarget.checked) {
	    addXBeachMarkers();
      } else {
        if (xbeach_markers) {
          xbeach_markers.remove();
     	}
      }
    })
  }

  var chk = document.getElementById('check_track');
  chk.checked = true;
  chk.addEventListener('change', (event) => {
    if (event.currentTarget.checked) {
		addCycloneTrack();
    } else {
		if (cyclone_track) {
		cyclone_track.remove();
     	}
    }
  })

  var chk = document.getElementById('check_track_ensemble');
  chk.checked = true;
  chk.addEventListener('change', (event) => {
    if (event.currentTarget.checked) {
		addCycloneTrackEnsemble();
    } else {
		if (cyclone_track_ensemble) {
		cyclone_track_ensemble.remove();
     	}
    }
  })

  var chk = document.getElementById('check_model_outlines');
  if (chk) {
    chk.checked = true;
    chk.addEventListener('change', (event) => {
      if (event.currentTarget.checked) {
        addModelOutlines();
      } else {
		if (model_outlines) {
		  model_outlines.remove();
     	}
      }
    })
  }


}
//addXBeachMarkers()