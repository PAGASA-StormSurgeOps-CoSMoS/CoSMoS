"""Utility to convert CoSMoS color map XML definitions to TOML format."""

import os

import cht_utils.fileio.xml as xml
import yaml

path = r"p:\11206085-onr-fhics\03_cosmos\configurations"
name = "map_contours"

xml_file = os.path.join(path, name + ".xml")
tml_file = os.path.join(path, name + ".toml")
yml_file = os.path.join(path, name + ".yml")
xml_obj = xml.xml2obj(xml_file)
config = {}
dct = xml_obj.__dict__
# color_range = []
color_range = []
for valobj in xml_obj.tile_map:
    name = valobj.name
    legend_text = valobj.legend_text[0].value
    rng = {}
    rng["name"] = name
    rng["legend_text"] = legend_text
    cntrs = []
    if hasattr(valobj, "contour"):
        #        clr = {}
        for contour in valobj.contour:
            cntr = {}
            cntr["lower"] = contour.lower[0].value
            cntr["upper"] = contour.upper[0].value
            cntr["rgb"] = contour.rgb[0].value
            cntr["text"] = contour.legend_text[0].value
            cntrs.append(cntr)
        rng["contour"] = cntrs
    #        color_range[name]["contour"] = cntrs
    else:
        clr = {}
        rng["color_map"] = valobj.color_map[0].value
        rng["lower"] = valobj.lower[0].value
        rng["upper"] = valobj.upper[0].value
        if hasattr(valobj, "step"):
            rng["step"] = valobj.step[0].value
        if hasattr(valobj, "scale"):
            rng["scale"] = valobj.scale[0].value

    color_range.append(rng)

#    val = valobj.value

# if key == "name":
#     key = None

# if key == "longname":
#     key = "long_name"

# if key == "type" or key == "cluster":
#     val = val.lower()

# if val == "no":
#     val = False
# elif val == "yes":
#     val = True

# if key == "priority":
#     key = None

# if key == "flowspinup":
#     if val != "none":
#         key = "flow_spinup_time"
#     else:
#         key = None

# if key == "wavespinup":
#     if val != "none":
#         key = "wave_spinup_time"
#     else:
#         key = None

# if key == "flownested":
#     if val != "none":
#         key = "flow_nested"
#     else:
#         key = None

# if key == "wavenested":
#     if val != "none":
#         key = "wave_nested"
#     else:
#         key = None
# if key == "coordsys":
#     key = "crs"
# if key == "coordsystype":
#     key = None


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


# if key:
#     config[key] = val


ccc = {}
ccc["color_range"] = color_range
# with open(tml_file, "w") as f:
#     new_toml_string = toml.dump(color_range, f)

with open(yml_file, "w") as f:
    new_toml_string = yaml.dump(ccc, f, sort_keys=False)


# xxx = toml.load(tml_file)

with open(yml_file, "r") as f:
    yyy = yaml.safe_load(f)

# yyy = yaml.load(yml_file)
pass
