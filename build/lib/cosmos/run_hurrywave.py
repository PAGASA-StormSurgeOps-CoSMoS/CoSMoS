"""HurryWave standalone job runner for CoSMoS.

Runs HurryWave model jobs on remote workers or in the cloud, including nesting,
ensemble member setup, tiling, and S3 data transfer.
"""

import datetime
import os
import platform
import sys

import boto3

# from cht_utils.argo import Argo
import cht_utils.fileops as fo
import pandas as pd
import xarray as xr
from cht_nesting import nest2
from cht_tiling import TiledWebMap
from cht_utils.fileio.yaml import yaml2dict
from cht_utils.probabilistic.prob_maps import merge_nc_his, merge_nc_map
from hydromt_hurrywave import HurrywaveModel


def _read_hm0max(
    hm0max_file: str, time_range=None, parameter: str = "hm0max"
) -> "np.ndarray":
    """Read maximum wave heights from HurryWave map output."""
    ds = xr.open_dataset(hm0max_file)
    data = ds[parameter]
    if time_range is not None:
        data = data.sel(timemax=slice(time_range[0], time_range[1]))
    result = data.max(dim="timemax").values
    ds.close()
    return result


def read_ensemble_members() -> list:
    with open("ensemble_members.txt") as f:
        ensemble_members = f.readlines()
    ensemble_members = [x.strip() for x in ensemble_members]
    return ensemble_members


def get_s3_client(config: dict):
    # Create an S3 client
    session = boto3.Session(
        aws_access_key_id=config["cloud"]["access_key"],
        aws_secret_access_key=config["cloud"]["secret_key"],
        region_name=config["cloud"]["region"],
    )
    return session.client("s3")


def prepare_ensemble(config: dict) -> None:
    # In case of ensemble, make folders for each ensemble member and copy necessary scripts to these folders
    # Read in the list of ensemble members
    ensemble_members = read_ensemble_members()
    for member in ensemble_members:
        print("Making folder for ensemble member " + member)
        # Make folder for ensemble member and copy all input files
        fo.mkdir(member)
        fo.copy_file(os.path.join("base_input", "run_job_2.py"), member)
        fo.copy_file(os.path.join("base_input", "config.yml"), member)
        fo.copy_file(os.path.join("base_input", "ensemble_members.txt"), member)


def prepare_single(config: dict, member: str = None) -> None:
    # Copying, nesting, spiderweb
    # We're already in the correct folder
    if config["run_mode"] == "cloud":
        # Initialize S3 client
        s3_client = get_s3_client(config)
        bucket_name = "cosmos-scenarios"

    if config["run_mode"] == "cloud":
        # Copy base input to member folder
        if config["ensemble"]:
            s3_key = (
                config["scenario"]
                + "/"
                + "models"
                + "/"
                + config["model"]
                + "/"
                + "base_input"
                + "/"
            )
        else:
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
    else:
        if config["ensemble"]:
            # Copy from input folder
            # We're already in the right member path
            fo.copy_file(os.path.join("..", "base_input", "*.*"), ".")

    # Spiderweb file: in local mode the per-member hurrywave.spw was staged
    # into the member folder during CoSMoS pre-process
    # (Model.write_meteo_input_files), so nothing to do here. In cloud mode it
    # still has to be pulled from S3.
    if config["ensemble"] and config["run_mode"] == "cloud":
        print("Downloading spiderweb file from S3 ...")
        s3_key = (
            config["scenario"]
            + "/"
            + "track_ensemble"
            + "/"
            + "spw"
            + "/ensemble_"
            + member
            + ".spw"
        )
        local_file_path = "/input/hurrywave.spw"
        try:
            s3_client.download_file(bucket_name, s3_key, local_file_path)
            print(f"File downloaded successfully to '{local_file_path}'")
        except Exception as e:
            print(f"Error: {e}")

    # Read HurryWave model (necessary for nesting)
    hw = HurrywaveModel(root=".", mode="r+")
    hw.name = config["model"]
    hw.type = "hurrywave"

    # Nesting
    if "wave_nested" in config:
        print("Nesting wave ...")
        # Get boundary conditions from overall model (Nesting 2)
        # If cloud mode, copy boundary files from S3
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
            config["wave_nested"]["overall_path"] = local_file_path

        # Get boundary conditions from overall model (Nesting 2)
        if config["ensemble"]:
            nest2(
                config["wave_nested"]["overall_type"],
                hw,
                output_path=os.path.join(config["wave_nested"]["overall_path"], member),
                bc_path=".",
            )
        else:
            # Deterministic
            nest2(
                config["wave_nested"]["overall_type"],
                hw,
                output_path=config["wave_nested"]["overall_path"],
                bc_path=".",
            )


def merge_ensemble(config: dict) -> None:
    print("Merging ...")
    if config["run_mode"] == "cloud":
        folder_path = "/input"
        his_output_file_name = os.path.join("/output/hurrywave_his.nc")
    #        map_output_file_name = os.path.join("/hurrywave_map.nc")
    else:
        folder_path = "./"
        his_output_file_name = "./output/hurrywave_his.nc"
        map_output_file_name = "./hurrywave_map.nc"
    output_path = "./output"
    os.makedirs("output", exist_ok=True)

    # Read in the list of ensemble members
    ensemble_members = read_ensemble_members()
    # Merge output files
    his_files = []
    map_files = []
    for member in ensemble_members:
        os.makedirs(os.path.join(output_path, member), exist_ok=True)
        if os.path.exists(os.path.join(folder_path, member, "hurrywave_his.nc")):
            his_files.append(os.path.join(folder_path, member, "hurrywave_his.nc"))
            fo.copy_file(
                os.path.join(folder_path, member, "hurrywave_his.nc"),
                os.path.join(output_path, member, "hurrywave_his.nc"),
            )
        if os.path.exists(os.path.join(folder_path, member, "hurrywave_sp2.nc")):
            fo.copy_file(
                os.path.join(folder_path, member, "hurrywave_sp2.nc"),
                os.path.join(output_path, member, "hurrywave_sp2.nc"),
            )
        map_files.append(os.path.join(folder_path, member, "hurrywave_map.nc"))

    merge_nc_his(
        his_files, ["point_hm0", "point_tp"], output_file_name=his_output_file_name
    )
    if "hm0_map" in config:
        merge_nc_map(map_files, ["hm0max"], output_file_name=map_output_file_name)
    # Copy restart files from the first ensemble member (restart files are the same for all members)
    fo.copy_file(
        os.path.join(folder_path, ensemble_members[0], "hurrywave.*.rst"), folder_path
    )


def map_tiles(config: dict) -> None:

    # Make flood map tiles
    if "hm0_map" in config:
        hm0_path = config["hm0_map"]["png_path"]
        index_path = config["hm0_map"]["index_path"]
        output_path = config["hm0_map"]["output_path"]

        if os.path.exists(index_path):
            print("Making wave map tiles for model " + config["model"] + " ...")

            # ... hour increments
            dtinc = config["hm0_map"]["interval"]

            # Wave map for the entire simulation
            dt1 = datetime.timedelta(hours=1)
            dt = datetime.timedelta(hours=dtinc)
            t0 = config["hm0_map"]["start_time"].replace(tzinfo=None)
            t1 = config["hm0_map"]["stop_time"].replace(tzinfo=None)

            requested_times = (
                pd.date_range(start=t0 + dt, end=t1, freq=str(dtinc) + "h")
                .to_pydatetime()
                .tolist()
            )

            color_values = config["hm0_map"]["color_map"]["contours"]

            pathstr = []
            for it, t in enumerate(requested_times):
                pathstr.append(
                    (t - dt).strftime("%Y%m%d_%HZ") + "_" + (t).strftime("%Y%m%d_%HZ")
                )
            pathstr.append(
                "combined_"
                + (t0).strftime("%Y%m%d_%HZ")
                + "_"
                + (t1).strftime("%Y%m%d_%HZ")
            )

            hm0max_file = os.path.join(output_path, "hurrywave_map.nc")

            if config["ensemble"]:
                varname = "hm0max_90"
            else:
                varname = "hm0max"

            try:
                # Wave map over dt-hour increments
                for it, t in enumerate(requested_times):
                    hm0max = _read_hm0max(
                        hm0max_file,
                        time_range=[t - dt + dt1, t + dt1],
                        parameter=varname,
                    )

                    png_path = os.path.join(
                        hm0_path,
                        config["scenario"],
                        config["cycle"],
                        config["hm0_map"]["name"],
                        pathstr[it],
                    )

                    twm = TiledWebMap(
                        png_path,
                        data=hm0max,
                        type="rgba",
                        parameter="hm0",
                        color_values=color_values,
                        index_path=index_path,
                        quiet=False,
                    )
                    twm.make()

                # Full simulation
                hm0max = _read_hm0max(
                    hm0max_file,
                    time_range=[t0 + dt1, t1 + dt1],
                    parameter=varname,
                )

                png_path = os.path.join(
                    hm0_path,
                    config["scenario"],
                    config["cycle"],
                    config["hm0_map"]["name"],
                    pathstr[-1],
                )

                twm = TiledWebMap(
                    png_path,
                    data=hm0max,
                    type="rgba",
                    parameter="hm0",
                    color_values=color_values,
                    index_path=index_path,
                    quiet=False,
                )
                twm.make()

            except Exception as e:
                print("An error occured while making wave map tiles: {}".format(str(e)))


def clean_up(config: dict) -> None:
    if config["ensemble"]:
        # Remove all ensemble members
        # Read in the list of ensemble members
        with open("ensemble_members.txt") as f:
            ensemble_members = f.readlines()
        ensemble_members = [x.strip() for x in ensemble_members]
        if config["run_mode"] == "cloud":
            s3_client = get_s3_client(config)
            bucket_name = "cosmos-scenarios"
            config["scenario"] + "/" + config["model"]
            for member in ensemble_members:
                s3key = (
                    config["scenario"]
                    + "/"
                    + "models"
                    + "/"
                    + config["model"]
                    + "/"
                    + member
                )
                # Delete folder from S3
                objects = s3_client.list_objects(Bucket=bucket_name, Prefix=s3key)
                for object in objects["Contents"]:
                    s3_client.delete_object(Bucket=bucket_name, Key=object["Key"])
        else:
            for member in ensemble_members:
                try:
                    fo.rmdir(member)
                    print("Directory has been removed successfully : " + member)
                except OSError as error:
                    print(error)
                    print("Directory can not be removed : " + member)


# SFINCS job script

member_name = None
option = sys.argv[1]

print("Running run_job.py")
print("Option: " + option)

# Read config file (config.yml)
config = yaml2dict("config.yml")

# Check if member is specified
member = None
if len(sys.argv) == 3:
    member = sys.argv[2]
    print("Member: " + member)

if option == "prepare_ensemble":
    # Prepare folders
    prepare_ensemble(config)

elif option == "simulate":
    # Never called in cloud mode
    # Make run string (platform dependent)
    if platform.system() == "Windows":
        # Use ".\" so the script is found even when cmd.exe is configured
        # with NoDefaultCurrentDirectoryInExePath=1 (which excludes CWD
        # from the executable search path).
        run_string = r"call .\run_simulation.bat"
    else:
        run_string = "source ./run_simulation.sh"
    if config["ensemble"]:
        # Read in the list of ensemble members
        ensemble_members = read_ensemble_members()
        # Loop through members
        curdir = os.getcwd()
        for member in ensemble_members:
            print("Running ensemble member " + member)
            os.chdir(member)
            # Run the Hurrywave model
            prepare_single(config, member=member)
            os.system(run_string)
            os.chdir(curdir)
    else:
        prepare_single(config)
        os.system(run_string)

elif option == "prepare_single":
    # Only occurs in cloud mode (running single is done in workflow)
    prepare_single(config, member=member)

# elif option == "simulate_single":
#     # Only called in cloud mode (should move this back to container?)
#     # Kick off cosmos-sfincs workflow (which runs this script with prepare_single, and then runs the sfincs docker)
#     # So effectively, it does the same as run consecutively running prepare_single and run_single
#     subfolder = config["scenario"] + "/" + "models" + "/" + config["model"]
#     if config["ensemble"]:
#         subfolder += "/" + member
#     print("Submitting member in " + subfolder)
#     w = Argo(config["cloud"]["host"], "sfincs-workflow")
#     w.submit_job(bucket_name="cosmos-scenarios",
#                  subfolder=subfolder,
#                  member=member)

elif option == "merge_ensemble":
    # Merge his and map files from ensemble members
    merge_ensemble(config)

elif option == "map_tiles":
    # Make map tiles
    map_tiles(config)

elif option == "clean_up":
    # Remove all ensemble members
    clean_up(config)
