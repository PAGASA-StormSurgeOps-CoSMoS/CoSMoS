"""Utility to batch-convert scenario XML files to TOML format."""

import os

import cht_utils.fileio.xml as xml
import cht_utils.fileops as fo
import toml

scenario_database_path = r"p:\11206085-onr-fhics\03_cosmos\scenarios"
scenario_list = fo.list_folders(os.path.join(scenario_database_path, "*"))
for name_path in scenario_list:
    name = os.path.basename(name_path).lower()
    xml_file = os.path.join(name_path, name + ".xml")

    print(xml_file)
    tml_file = os.path.join(name_path, "scenario.toml")

    try:
        xml_obj = xml.xml2obj(xml_file)

        scenario = {}
        scenario["model"] = []
        scenario["cluster"] = []

        dct = xml_obj.__dict__
        for key in dct:
            valobj = getattr(xml_obj, key)
            if key == "model":
                for model in valobj:
                    mdl = {}
                    dct2 = model.__dict__
                    for key2 in dct2:
                        valobj2 = getattr(model, key2)
                        val2 = valobj2[0].value
                        mdl[key2] = val2
                    scenario["model"].append(mdl)

            elif key == "cluster":
                for cluster in valobj:
                    clsr = {}
                    dct2 = cluster.__dict__
                    for key2 in dct2:
                        valobj2 = getattr(cluster, key2)
                        val2 = valobj2[0].value
                        clsr[key2] = val2
                    scenario["cluster"].append(clsr)

            else:
                val = valobj[0].value

                if key == "name":
                    key = None

                if key == "longname":
                    key = "long_name"

                if key == "type" or key == "cluster":
                    val = val.lower()

                if val == "no":
                    val = False
                elif val == "yes":
                    val = True

                if key == "priority":
                    key = None

                if key == "flowspinup":
                    if val != "none":
                        key = "flow_spinup_time"
                    else:
                        key = None

                if key == "wavespinup":
                    if val != "none":
                        key = "wave_spinup_time"
                    else:
                        key = None

                if key == "flownested":
                    if val != "none":
                        key = "flow_nested"
                    else:
                        key = None

                if key == "wavenested":
                    if val != "none":
                        key = "wave_nested"
                    else:
                        key = None
                if key == "coordsys":
                    key = "crs"
                if key == "coordsystype":
                    key = None

                # # Read polygon around model
                # polygon_file  = os.path.join(self.path, "misc", self.name + ".txt")
                # if os.path.exists(polygon_file):
                #     df = pd.read_csv(polygon_file, index_col=False, header=None,
                #          delim_whitespace=True, names=['x', 'y'])
                #     xy = df.to_numpy()
                #     self.polygon = path.Path(xy)
                #     if not self.xlim:
                #         self.xlim = [self.polygon.vertices.min(axis=0)[0],
                #                      self.polygon.vertices.max(axis=0)[0]]
                #         self.ylim = [self.polygon.vertices.min(axis=0)[1],
                #                      self.polygon.vertices.max(axis=0)[1]]

                # # Stations
                # if hasattr(xml_obj, "station"):

                #     for istat in range(len(xml_obj.station)):

                #         # Find matching stations from complete stations list

                #         name = xml_obj.station[istat].value
                #         self.add_stations(name)

                if key:
                    scenario[key] = val

        ccc = {}
        ccc["scenario"] = scenario
        with open(tml_file, "w") as f:
            new_toml_string = toml.dump(scenario, f)

        xxx = toml.load(tml_file)
        pass
    except FileNotFoundError:
        print("error " + name)
