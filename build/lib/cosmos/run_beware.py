"""BEWARE standalone job runner for CoSMoS.

Runs BEWARE model jobs on remote workers or in the cloud, including nesting,
ensemble member setup, tiling, and S3 data transfer.
"""

# import boto3
import os
import platform
import sys

import cht_utils.fileops as fo
from cht_beware.beware import BEWARE
from cht_nesting import nest2
from cht_utils.fileio.yaml import yaml2dict
from cht_utils.probabilistic.prob_maps import merge_nc_his

# from cht_utils.argo import Argo


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

    # Read BEWARE model (necessary for nesting)
    bw = BEWARE("beware.inp")
    bw.name = config["model"]
    bw.type = "beware"
    bw.path = "."

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
        if config["ensemble"]:
            nest2(
                config["flow_nested"]["overall_type"],
                bw,
                output_path=os.path.join(config["flow_nested"]["overall_path"], member),
                boundary_water_level_correction=zcor,
                option="flow",
                bc_path=".",
            )
        else:
            # Deterministic
            nest2(
                config["flow_nested"]["overall_type"],
                bw,
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
        if config["ensemble"]:
            nest2(
                config["wave_nested"]["overall_type"],
                bw,
                output_path=os.path.join(config["wave_nested"]["overall_path"], member),
                option="wave",
                bc_path=".",
            )
        else:
            # Deterministic
            nest2(
                config["wave_nested"]["overall_type"],
                bw,
                output_path=config["wave_nested"]["overall_path"],
                option="wave",
                bc_path=".",
            )


def merge_ensemble(config: dict) -> None:
    print("Merging ...")
    if config["run_mode"] == "cloud":
        folder_path = "/input"
        his_output_file_name = os.path.join("/output/beware_his.nc")
    else:
        folder_path = "./"
        his_output_file_name = "./output/beware_his.nc"
    output_path = "./output"
    os.makedirs("output", exist_ok=True)

    # Read in the list of ensemble members
    ensemble_members = read_ensemble_members()
    # Merge output files
    his_files = []
    for member in ensemble_members:
        os.makedirs(os.path.join(output_path, member), exist_ok=True)
        his_files.append(os.path.join(folder_path, member, "beware_his.nc"))
        fo.copy_file(
            os.path.join(folder_path, member, "beware_his.nc"),
            os.path.join(output_path, member, "beware_his.nc"),
        )
    merge_nc_his(
        his_files, ["R2", "R2_setup", "WL"], output_file_name=his_output_file_name
    )


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


# BEWARE job script

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
    if platform.system() == "Windows":
        run_string = "call run_simulation.bat"
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
            # Run the BEWARE model
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

elif option == "clean_up":
    # Remove all ensemble members
    clean_up(config)
