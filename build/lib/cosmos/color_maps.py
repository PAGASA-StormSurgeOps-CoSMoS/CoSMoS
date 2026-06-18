"""Color map and contour definitions for CoSMoS map output.

Reads color range definitions from TOML configuration files and builds
contour specifications used for generating tiled map visualizations.
"""

import os

import numpy as np
import toml
from cht_utils.colors import rgb2hex


def read_color_maps(file_name: str) -> dict:
    """Read color map and contour definitions from a TOML configuration file.

    Parameters
    ----------
    file_name : str
        Path to the TOML file containing ``color_range`` definitions.

    Returns
    -------
    dict
        Mapping of contour set name to contour specification dict.
    """
    map_contours = {}

    with open(file_name, "r") as f:
        # clrs = yaml.safe_load(f)
        clrs = toml.load(f)

    # Map contours
    maps = clrs["color_range"]
    for tm in maps:
        map_type = {}
        #        map_type["name"] = tm["name"]
        map_type["string"] = tm["legend_text"]
        map_type["contours"] = []
        if "scale" not in tm:
            scale = "linear"
        else:
            scale = tm["scale"]

        if "contour" in tm:
            # Contours are provided

            for c in tm["contour"]:
                cnt = {}
                cnt["string"] = c["text"]
                cnt["lower_value"] = c["lower"]
                cnt["upper_value"] = c["upper"]
                cnt["rgb"] = c["rgb"]
                cnt["hex"] = rgb2hex(tuple(cnt["rgb"]))

                map_type["contours"].append(cnt)
        else:
            # Contours from contour map in config folder

            filename = os.path.join(
                os.path.dirname(file_name), tm["color_map"] + ".txt"
            )

            vals = np.loadtxt(filename)
            nrows = np.shape(vals)[0]
            ncols = np.shape(vals)[1]
            if ncols == 4:
                v = np.squeeze(vals[:, 0])
                r = np.squeeze(vals[:, 1])
                g = np.squeeze(vals[:, 2])
                b = np.squeeze(vals[:, 3])
            else:
                v = np.arange(0.0, 1.000001, 1.0 / (nrows - 1))
                r = np.squeeze(vals[:, 0])
                g = np.squeeze(vals[:, 1])
                b = np.squeeze(vals[:, 2])

            if scale == "linear":
                zmin = tm["lower"]
                zmax = tm["upper"]
                step = tm["step"]
                nsteps = round((zmax - zmin) / step + 2)

                for i in range(nsteps):
                    # Interpolate
                    zl = zmin + (i - 1) * step
                    zu = zl + step
                    z = i / ((nsteps - 1) * 1.0)
                    rr = round(np.interp(z, v, r))
                    gg = round(np.interp(z, v, g))
                    bb = round(np.interp(z, v, b))
                    rgb = [rr, gg, bb]

                    cnt = {}
                    if i == 0:
                        cnt["string"] = "< " + str(zmin)
                        cnt["lower_value"] = -1.0e6
                        cnt["upper_value"] = zu
                    elif i == nsteps - 1:
                        cnt["string"] = "> " + str(zmax)
                        cnt["lower_value"] = zl
                        cnt["upper_value"] = 1.0e6
                    else:
                        cnt["string"] = str(zl) + " - " + str(zu)
                        cnt["lower_value"] = zl
                        cnt["upper_value"] = zu
                    cnt["rgb"] = rgb
                    cnt["hex"] = rgb2hex(tuple(rgb))

                    map_type["contours"].append(cnt)

            else:
                # Logarithmic

                zmin = tm["lower"]
                zmax = tm["upper"]

                if scale == "log125":
                    nit = 10
                    zz = np.zeros(nit * 3)
                    k = -1
                    for i in range(nit):
                        k = k + 1
                        if i == 0:
                            zz[k] = 1.0e-4
                        else:
                            zz[k] = zz[k - 1] * 2
                        k = k + 1
                        zz[k] = zz[k - 1] * 2
                        k = k + 1
                        zz[k] = zz[k - 1] * 2.5
                elif scale == "log16":
                    nit = 10
                    zz = np.zeros(nit * 5)
                    k = -1
                    for i in range(nit):
                        k = k + 1
                        # 0.1
                        if i == 0:
                            zz[k] = 1.0e-4
                        else:
                            zz[k] = zz[k - 1] * 100 / 65
                        k = k + 1
                        # 0.15
                        zz[k] = zz[k - 1] * 3 / 2
                        k = k + 1
                        # 0.25
                        zz[k] = zz[k - 1] * 5 / 3
                        k = k + 1
                        # 0.40
                        zz[k] = zz[k - 1] * 8 / 5
                        k = k + 1
                        # 0.65
                        zz[k] = zz[k - 1] * 65 / 40
                elif scale == "log16":
                    nit = 10
                    zz = np.zeros(nit * 5)
                    k = -1
                    for i in range(nit):
                        k = k + 1
                        # 0.1
                        if i == 0:
                            zz[k] = 1.0e-4
                        else:
                            zz[k] = zz[k - 1] * 100 / 65
                        k = k + 1
                        # 0.15
                        zz[k] = zz[k - 1] * 3 / 2
                        k = k + 1
                        # 0.25
                        zz[k] = zz[k - 1] * 5 / 3
                        k = k + 1
                        # 0.40
                        zz[k] = zz[k - 1] * 8 / 5
                        k = k + 1
                        # 0.65
                        zz[k] = zz[k - 1] * 65 / 40
                elif scale == "log121":
                    # 1 1.2 1.5 1.8 2.2 2.6 3.2 3.8 4.6 5.5 6.8 8.2 10
                    nit = 10
                    zz = np.zeros(nit * 12)
                    k = -1
                    for i in range(nit):
                        k = k + 1
                        # 0.1
                        if i == 0:
                            zz[k] = 1.0e-4
                        else:
                            zz[k] = zz[k - 1] * 50 / 41
                        # 1.2
                        k = k + 1
                        zz[k] = zz[k - 1] * 6 / 5
                        # 1.5
                        k = k + 1
                        zz[k] = zz[k - 1] * 5 / 4
                        # 1.8
                        k = k + 1
                        zz[k] = zz[k - 1] * 6 / 5
                        # 2.2
                        k = k + 1
                        zz[k] = zz[k - 1] * 11 / 9
                        # 2.6
                        k = k + 1
                        zz[k] = zz[k - 1] * 13 / 11
                        # 3.2
                        k = k + 1
                        zz[k] = zz[k - 1] * 16 / 13
                        # 3.8
                        k = k + 1
                        zz[k] = zz[k - 1] * 19 / 16
                        # 4.6
                        k = k + 1
                        zz[k] = zz[k - 1] * 23 / 19
                        # 5.5
                        k = k + 1
                        zz[k] = zz[k - 1] * 55 / 46
                        # 6.8
                        k = k + 1
                        zz[k] = zz[k - 1] * 68 / 55
                        # 8.2
                        k = k + 1
                        zz[k] = zz[k - 1] * 41 / 34

                i0 = np.where(zz >= zmin - 1.0e-6)[0][0]
                i1 = np.where(zz >= zmax - 1.0e-6)[0][0]

                nsteps = i1 - i0 + 1

                k = -1
                for i in range(i0, i1 + 2):
                    k = k + 1

                    # Interpolate
                    z = k / (nsteps * 1.0)
                    rr = round(np.interp(z, v, r))
                    gg = round(np.interp(z, v, g))
                    bb = round(np.interp(z, v, b))
                    rgb = [rr, gg, bb]

                    # cnt={}
                    # if k==0:
                    #     cnt["string"] = "< " + str(zmin)
                    #     cnt["lower_value"] = -1.0e6
                    #     cnt["upper_value"] = zz[i]
                    # elif i==nsteps - 1:
                    #     cnt["string"] = "> " + str(zmax)
                    #     cnt["lower_value"] = zz[i]
                    #     cnt["upper_value"] = 1.0e6
                    # else:
                    #     cnt["string"] = str(zz[i]) + " - " + str(zz[i + 1])
                    #     cnt["lower_value"] = zz[i]
                    #     cnt["upper_value"] = zz[i + 1]
                    cnt = {}
                    # The number of decimals should depend on zmin, zmax and zz
                    # If they are greater than 1, use one decimal. If they are lower than 1, use 2 decimals. If they are lower than 0.1, use 3 decimals, etc.

                    if k == 0:
                        if zmin >= 1.0:
                            fmt = ".1f"
                        elif zmin >= 0.1:
                            fmt = ".2f"
                        else:
                            fmt = ".3f"
                        cnt["string"] = "< " + f"{zmin:{fmt}}"
                        cnt["lower_value"] = -1.0e6
                        cnt["upper_value"] = float(zz[i])
                    # elif k==nsteps - 1:
                    elif k == nsteps:
                        if zmax >= 1.0:
                            fmt = ".1f"
                        elif zmax >= 0.1:
                            fmt = ".2f"
                        else:
                            fmt = ".3f"
                        cnt["string"] = "> " + f"{zmax:{fmt}}"
                        cnt["lower_value"] = float(zz[i - 1])
                        cnt["upper_value"] = 1.0e6
                    else:
                        if zz[i - 1] >= 1.0:
                            fmt1 = ".1f"
                        elif zz[i - 1] >= 0.1:
                            fmt1 = ".2f"
                        else:
                            fmt = ".3f"
                        if zz[i] >= 1.0:
                            fmt2 = ".1f"
                        elif zz[i] >= 0.1:
                            fmt2 = ".2f"
                        else:
                            fmt2 = ".3f"
                        cnt["string"] = (
                            f"{zz[i - 1]:{fmt1}}" + " - " + f"{zz[i]:{fmt2}}"
                        )
                        cnt["lower_value"] = float(zz[i - 1])
                        cnt["upper_value"] = float(zz[i])
                    cnt["rgb"] = rgb
                    cnt["hex"] = rgb2hex(tuple(rgb))

                    map_type["contours"].append(cnt)

            map_type["contours"] = map_type["contours"][::-1]

        map_contours[tm["name"]] = map_type

    return map_contours
