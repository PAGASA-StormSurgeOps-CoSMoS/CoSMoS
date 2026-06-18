"""Utility to batch-convert model database XML files to TOML format."""

import os

import cht_utils.fileio.xml as xml
import cht_utils.fileops as fo
import toml

model_database_path = r"p:\11206085-onr-fhics\03_cosmos\models"
region_list = fo.list_folders(os.path.join(model_database_path, "*"))
for region_path in region_list:
    region_name = os.path.basename(region_path)
    type_list = fo.list_folders(os.path.join(region_path, "*"))
    for type_path in type_list:
        type_name = os.path.basename(type_path)
        name_list = fo.list_folders(os.path.join(type_path, "*"))
        for name_path in name_list:
            name = os.path.basename(name_path).lower()

            # Check if xml file exists
            xml_file = os.path.join(name_path, name + ".xml")
            tml_file = os.path.join(name_path, "model.toml")

            print(name)

            try:
                xml_obj = xml.xml2obj(xml_file)

                model = {}
                dct = xml_obj.__dict__
                for key in dct:
                    valobj = getattr(xml_obj, key)
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

                    if key == "station":
                        val = [val]

                    if key == "flow_nesting_point_1":
                        key = "flow_nesting_points"
                        val = [[float(val.split(",")[0]), float(val.split(",")[1])]]

                    if key == "flow_nesting_point_2":
                        coor_2 = [float(val.split(",")[0]), float(val.split(",")[1])]
                        model["flow_nesting_points"].append(coor_2)
                        key = None

                    if key == "wave_nesting_point_1":
                        key = "wave_nesting_point"
                        val = [float(val.split(",")[0]), float(val.split(",")[1])]

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
                        model[key] = val

                if (
                    model["type"] == "sfincs"
                    or model["type"] == "hurrywave"
                    or model["type"] == "xbeach"
                ):
                    if "runid" in model:
                        model.pop("runid")

                with open(tml_file, "w") as f:
                    new_toml_string = toml.dump(model, f)

                xxx = toml.load(tml_file)

                pass
            except Exception:
                print("error " + name)
