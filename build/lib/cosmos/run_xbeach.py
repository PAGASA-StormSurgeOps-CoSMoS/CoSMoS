"""XBeach standalone job runner for CoSMoS.

Runs XBeach model jobs on remote workers or in the cloud, including nesting,
tiling, and S3 data transfer.
"""

import datetime
import os
import platform
import sys

import boto3

# from cht_utils.argo import Argo
import cht_utils.fileops as fo
import xarray as xr
from cht_nestingp import nest2
from cht_tiling import TiledWebMap
from cht_utils.fileio.yaml import yaml2dict
from cht_xbeach.xbeach import XBeach


def get_s3_client(config: dict):
    # Create an S3 client
    session = boto3.Session(
        aws_access_key_id=config["cloud"]["access_key"],
        aws_secret_access_key=config["cloud"]["secret_key"],
        region_name=config["cloud"]["region"],
    )
    return session.client("s3")


def prepare_single(config: dict) -> None:
    # Copying, nesting
    # We're already in the correct folder
    if config["run_mode"] == "cloud":
        # Initialize S3 client
        s3_client = get_s3_client(config)
        bucket_name = "cosmos-scenarios"

        # Copy base input folder
        s3_key = config["scenario"] + "/" + "models" + "/" + config["model"] + "/"
        local_file_path = "/input/"
        objects = s3_client.list_objects(Bucket=bucket_name, Prefix=s3_key)
        if "Contents" in objects:
            for object in objects["Contents"]:
                key = object["Key"]
                # Only download files in main folder, not in subfolders
                if key[-1] == "/":
                    continue
                if "/" in key.replace(s3_key, ""):
                    continue
                local_path = os.path.join(local_file_path, os.path.basename(key))
                print("Copying " + key + " to " + local_path)
                s3_client.download_file(bucket_name, key, local_path)

    # Read XBeach model (necessary for nesting)
    xb = XBeach(input_file="params.txt", get_boundary_coordinates=False)
    xb.name = config["model"]
    xb.type = "xbeach"
    xb.path = "."

    # read tref and tstop and convert stftime to datetime (needed for nesting, but not in params)
    xb.tref = datetime.datetime.strptime(config["xbeach"]["tref"], "%Y%m%d %H%M%S")
    xb.tstop = datetime.datetime.strptime(config["xbeach"]["tstop"], "%Y%m%d %H%M%S")

    flow_nesting_points = config["xbeach"]["flow_nesting_points"]

    # this is very double but needed for the nesting on different machines than the main-node
    xb.flow_boundary_point[len(flow_nesting_points) :] = []
    for ipnt, pnt in enumerate(flow_nesting_points):
        xb.flow_boundary_point[ipnt].name = str(ipnt + 1).zfill(4)
        xb.flow_boundary_point[ipnt].geometry.x = pnt[0]
        xb.flow_boundary_point[ipnt].geometry.y = pnt[1]

    wave_nesting_point = config["xbeach"]["wave_nesting_point"]
    xb.wave_boundary_point[0].name = str(1).zfill(4)
    xb.wave_boundary_point[0].geometry.x = wave_nesting_point[0]
    xb.wave_boundary_point[0].geometry.y = wave_nesting_point[1]

    xb.zb_deshoal = config["xbeach"]["zb_deshoal"]

    # Nesting
    if "flow_nested" in config:
        print("Nesting flow ...")
        # Get boundary conditions from overall model (Nesting 2)
        # Correct boundary water levels. Assuming that output from overall
        # model is in MSL !!!
        zcor = (
            config["flow_nested"]["boundary_water_level_correction"]
            - config["vertical_reference_level_difference_with_msl"]
        )
        # If cloud mode, copy boundary files from S3
        if config["run_mode"] == "cloud":
            file_name = config["flow_nested"]["overall_file"]
            s3_key = (
                config["scenario"]
                + "/"
                + "models"
                + "/"
                + config["flow_nested"]["overall_model"]
                + "/"
                + file_name
            )
            local_file_path = "/input/boundary"
            fo.mkdir(local_file_path)
            # Download the file from S3
            s3_client.download_file(
                bucket_name,
                s3_key,
                os.path.join(local_file_path, os.path.basename(s3_key)),
            )
            # Change path in config
            config["flow_nested"]["overall_path"] = local_file_path

        # Get boundary conditions from overall model (Nesting 2)
        # Deterministic
        nest2(
            config["flow_nested"]["overall_type"],
            xb,
            output_path=config["flow_nested"]["overall_path"],
            boundary_water_level_correction=zcor,
            option="flow",
            bc_path=".",
        )

    if "wave_nested" in config:
        print("Nesting wave ...")
        # Get boundary conditions from overall model (Nesting 2)
        if config["run_mode"] == "cloud":
            file_name = config["wave_nested"]["overall_file"]
            s3_key = (
                config["scenario"]
                + "/"
                + "models"
                + "/"
                + config["wave_nested"]["overall_model"]
                + "/"
                + file_name
            )
            local_file_path = "/input/boundary"
            fo.mkdir(local_file_path)
            # Download the file from S3
            s3_client.download_file(
                bucket_name,
                s3_key,
                os.path.join(local_file_path, os.path.basename(s3_key)),
            )
            # Change path in config
            config["flow_nested"]["overall_path"] = local_file_path

        # Get boundary conditions from overall model (Nesting 2)
        # Deterministic
        nest2(
            config["wave_nested"]["overall_type"],
            xb,
            output_path=config["wave_nested"]["overall_path"],
            option="timeseries",
            bc_path=".",
        )


def map_tiles(config: dict) -> None:

    # Make flood map tiles
    if "sedero_map" in config:
        # Make SFINCS object
        xb = XBeach()

        print("Making maps ...")

        # Get paths from config
        name = config["sedero_map"]["name"]
        index_path = config["sedero_map"]["index_path"]
        output_path = config["sedero_map"]["output_path"]
        png_path = os.path.join(
            config["sedero_map"]["png_path"], config["scenario"], config["cycle"]
        )

        # Create paths
        sedero_map_path = os.path.join(png_path, "sedero")
        zb0_map_path = os.path.join(png_path, "zb0")
        zbend_map_path = os.path.join(png_path, "zbend")

        if os.path.exists(index_path):
            # settings
            try:
                # read xbeach output
                output_file = os.path.join(output_path, "xboutput.nc")
                dt = xr.open_dataset(output_file)
            except Exception as e:
                print("An error occured while reading xbeach output: ", str(e))
                return

            # get start and stop time to determine the pathname
            t0 = config["sedero_map"]["start_time"].replace(tzinfo=None)
            t1 = config["sedero_map"]["stop_time"].replace(tzinfo=None)

            pathstr = []
            pathstr.append(
                (t0).strftime("%Y%m%d_%HZ") + "_" + (t1).strftime("%Y%m%d_%HZ")
            )

            var = "sedero"
            elev_min = -2
            # mask xbeach output based on a min elevation of the initial topobathymetry
            val = dt[var][-1, :, :].where(dt["zb"][0, :, :] > elev_min)
            val_masked = val.values

            # make pngs for sedimentoation/erosion
            print("Making sedimenation/erosion tiles for model " + name)
            make_sedero_tiles(
                config,
                val_masked,
                index_path,
                os.path.join(sedero_map_path, pathstr[0]),
            )
            print("Sedimentation/erosion tiles done.")

            # make pngs for bedlevels (pre- and post-storm)
            zb0 = dt["zb"][0, :, :].values
            zbend = dt["zb"][-1, :, :].values
            print("Making bedlevel tiles for model " + name)
            make_bedlevel_tiles(
                config, zb0, index_path, os.path.join(zb0_map_path, pathstr[0])
            )
            make_bedlevel_tiles(
                config, zbend, index_path, os.path.join(zbend_map_path, pathstr[0])
            )
            print("Bed level tiles done.")


def make_sedero_tiles(
    config: dict, sedero, index_path: str, sedero_map_path: str
) -> None:

    color_values = config["sedero_map"]["color_map"]["contours"]

    twm = TiledWebMap(
        sedero_map_path,
        data=sedero,
        type="rgba",
        parameter="sedero",
        color_values=color_values,
        index_path=index_path,
        quiet=True,
    )
    twm.make()


def make_bedlevel_tiles(
    config: dict, bedlevel, index_path: str, bedlevel_map_path: str
) -> None:

    color_values = config["sedero_map"]["color_map_zb"]["contours"]

    twm = TiledWebMap(
        bedlevel_map_path,
        data=bedlevel,
        type="rgba",
        parameter="bed_level",
        color_values=color_values,
        index_path=index_path,
        quiet=True,
    )
    twm.make()


# XBEACH job script

option = sys.argv[1]

print("Running run_job.py")
print("Option: " + option)

# Read config file (config.yml)
config = yaml2dict("config.yml")

if option == "simulate":
    # Make run string (platform dependent)
    if platform.system() == "Windows":
        run_string = "call run_simulation.bat"
    else:
        run_string = "source ./run_simulation.sh"

    prepare_single(config)
    os.system(run_string)

elif option == "map_tiles":
    # Make flood map tiles
    map_tiles(config)
