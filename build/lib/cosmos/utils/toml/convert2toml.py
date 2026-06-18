"""Utility to convert various XML and YAML configuration files to TOML format."""

# Convert files to toml format
import os

import cht.misc.fileops as fo
import cht.misc.xmlkit as xml
import toml
from cht.misc.misc_tools import yaml2dict


def xml2dict(element) -> dict:
    if len(element) == 0:
        return element.text
    else:
        return {child.tag: xml2dict(child) for child in element}


def xml2toml(
    foldername: str = None,
    file_list: list = None,
    format: str = "xml",
    items: list = None,
) -> None:
    # Get all files of format in foldername
    if foldername is not None:
        file_list = fo.list_files(foldername + "/*." + format)

    for file in file_list:
        if file.endswith(".xml"):
            xml_obj = xml.xml2obj(file)
            dct = xml_obj.__dict__

            data = {}
            if items is not None:
                for key in items:
                    data[key] = []

            for key in dct:
                valobj = getattr(xml_obj, key)
                if key in items:
                    for item in valobj:
                        mdl = {}
                        dct2 = item.__dict__
                        for key2 in dct2:
                            valobj2 = getattr(item, key2)
                            val2 = valobj2[0].value
                            mdl[key2] = val2
                        data[key].append(mdl)
                else:
                    val = valobj[0].value
                    if val == "no":
                        val = False
                    elif val == "yes":
                        val = True
                    data[key] = val

        elif file.endswith(".yml"):
            data = yaml2dict(file)

        # Convert content to TOML
        tomldata = toml.dumps(data)
        newfilename = os.path.splitext(file)[0] + ".toml"
        newfile = open(newfilename, "w")
        newfile.write(tomldata)
        newfile.close()


xml2toml(
    file_list=[
        r"..\cosmos\meteo\meteo_subsets.xml",
    ],
    items=[
        "meteo_subset",
    ],
)

folder = r"..\cosmos\configuration\stations\\"
xml2toml(
    foldername=folder,
    items=[
        "station",
    ],
)

folder = r"..\cosmos\model_database\puerto_rico3\sfincs\\"
name_list = fo.list_folders(os.path.join(folder, "*"))

for name_path in name_list:
    name = os.path.basename(name_path).lower()

    # Check if xml file exists
    tml_file = os.path.join(name_path, "model.toml")
    data = toml.load(tml_file)

    for key, value in data.items():
        if isinstance(value, list):
            data[key] = [
                os.path.splitext(item)[0] + ".toml" if item.endswith(".xml") else item
                for item in value
            ]

            # data[key] = os.path.splitext(value)[0] + '.toml'

    with open(tml_file, "w") as f:
        new_toml_string = toml.dump(data, f)
