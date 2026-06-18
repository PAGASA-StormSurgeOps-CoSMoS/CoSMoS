"""Tile merging for CoSMoS cloud deployments.

Merges map tiles from individual model outputs into shared tile directories
on S3 by compositing PNG images with alpha blending.
"""

import os
import shutil

# from bulkboto3 import BulkBoto3
import tarfile
from multiprocessing.pool import ThreadPool

import boto3
import numpy as np
from cht_utils.fileio.yaml import yaml2dict
from PIL import Image


# Helper class for cloud functions, note this is a copy of necessary functionalities of cosmos_cloud
class Cloud:
    def __init__(self, config: dict) -> None:
        # Create a session using your AWS credentials (or configure it in other ways)
        session = boto3.Session(
            aws_access_key_id=config["cloud"]["access_key"],
            aws_secret_access_key=config["cloud"]["secret_key"],
            region_name=config["cloud"]["region"],
        )
        # Create an S3 client
        self.s3_client = session.client("s3")

        # entrypoint_url = "https://eu-west-1.console.aws.amazon.com/s3/home?region=eu-west-1"
        # self.bulkboto_agent = BulkBoto3(
        #     resource_type="s3",
        #     endpoint_url=entrypoint_url,
        #     aws_access_key_id=config["cloud"]["access_key"],
        #     aws_secret_access_key=config["cloud"]["secret_key"],
        #     max_pool_connections=300,
        #     verbose=True,
        # )

    def list_folders(self, bucket_name: str, s3_folder: str) -> list:
        if s3_folder[-1] != "/":
            s3_folder = s3_folder + "/"
        folders = []
        paginator = self.s3_client.get_paginator("list_objects_v2")
        iterator = paginator.paginate(
            Bucket=bucket_name, Prefix=s3_folder, Delimiter="/"
        )
        for page in iterator:
            for subfolder in page.get("CommonPrefixes", []):
                subfolder_name = subfolder["Prefix"].rstrip("/").split("/")[-1]
                folders.append(subfolder_name)
        return folders

    def upload_folder(
        self, bucket_name, local_folder, s3_folder, parallel=True, quiet=True
    ):
        local_folder = local_folder.replace("\\\\", "\\")
        local_folder = local_folder.replace("\\", "/")
        # Recursively list all files
        flist = list_all_files(local_folder)

        #        for file in flist:
        #            file1 = file.replace('\\','/')
        #            file1 = file1.replace(local_folder,'')
        #            s3_key = s3_folder + file1
        #            try:
        #                self.s3_client.upload_file(file, bucket_name, s3_key)
        #            except Exception as e:
        #                raise Exception("Failed to upload {}: {}".format(file, e))
        #            if not quiet:
        #                print("Uploaded " + os.path.basename(file))

        if parallel:
            pool = ThreadPool()
            pool.starmap(
                upf,
                [
                    (file, local_folder, s3_folder, bucket_name, self.s3_client, quiet)
                    for file in flist
                ],
            )
        else:
            for file in flist:
                upf(file, local_folder, s3_folder, bucket_name, self.s3_client, quiet)

    def bulk_upload_folder(
        self, bucket_name: str, local_folder: str, s3_folder: str, num_threads: int = 8
    ) -> None:
        local_folder = local_folder.replace("\\\\", "\\")
        local_folder = local_folder.replace("\\", "/")
        self.bulkboto_agent.upload_dir_to_storage(
            bucket_name=bucket_name,
            local_dir=local_folder,
            storage_dir=s3_folder,
            n_threads=num_threads,
        )

    def download_and_extract_tgz(
        self, bucket_name: str, s3_folder: str, local_folder: str
    ) -> None:
        """
        Download and extract a .tgz file from S3.
        """
        local_tgz_path = os.path.join("/tmp", os.path.basename(s3_folder))
        print("local_tgz_path: ", local_tgz_path)

        # Download the .tgz file
        try:
            print("Downloading {} to {}".format(s3_folder, local_tgz_path))
            self.s3_client.download_file(bucket_name, s3_folder, local_tgz_path)
        except Exception as e:
            raise Exception("Failed to download {}: {}".format(s3_folder, e))

        # Extract the .tgz file
        try:
            with tarfile.open(local_tgz_path, "r:gz") as tar:
                print("Extracting {} to {}".format(local_tgz_path, local_folder))
                tar.extractall(path=local_folder)
        except Exception as e:
            raise Exception("Failed to extract {}: {}".format(local_tgz_path, e))

        # Clean up the downloaded .tgz file
        print("Removing {}".format(local_tgz_path))
        os.remove(local_tgz_path)

    def check_file_exists(self, bucket_name: str, s3_key: str) -> bool:
        from botocore.exceptions import ClientError

        try:
            self.s3_client.head_object(Bucket=bucket_name, Key=s3_key)
            return True
        except ClientError as e:
            if e.response["Error"]["Code"] == "404":
                return False
            else:
                raise


def upf(
    file: str,
    local_folder: str,
    s3_folder: str,
    bucket_name: str,
    s3_client,
    quiet: bool,
) -> None:
    file1 = file.replace("\\", "/")
    file1 = file1.replace(local_folder, "")
    s3_key = s3_folder + file1
    s3_client.upload_file(file, bucket_name, s3_key)
    if not quiet:
        print("Uploaded " + file + " to " + s3_key + " in bucket " + bucket_name)
        # print("Uploaded " + file)


def list_all_files(src: str) -> list:
    # Recursively list all files and folders in a folder
    import pathlib

    pth = pathlib.Path(src)
    pthlst = list(pth.rglob("*"))
    lst = []
    for f in pthlst:
        if f.is_file():
            lst.append(str(f))
    return lst


# Helper functions, these should be put into cht_tiling?
def merge_images(image1_path: str, image2_path: str, output_path: str) -> None:
    """
    Merge two images by overlaying image2 on image1 and save the result.
    """
    with Image.open(image1_path) as img1, Image.open(image2_path) as img2:
        rgb1 = np.array(img1)  # existing image
        rgb2 = np.array(img2)  # new image
        isum = np.sum(rgb1, axis=2)  # sum of the existing image
        # replace the existing image with the new image where the existing image is zero
        rgb1[isum == 0, :] = rgb2[isum == 0, :]
        im = Image.fromarray(rgb1)
        im.save(output_path)


def merge_model_tiles(model_tiles: str, merged_tiles: str) -> None:
    """
    Process tiles from multiple models and merge them if they already exist in the shared directory.
    """
    for root, _, files in os.walk(model_tiles):
        for file in files:
            if file.endswith(".png"):
                # Construct the full file paths
                src_path = os.path.join(root, file)
                relative_path = os.path.relpath(src_path, model_tiles)
                dest_path = os.path.join(merged_tiles, relative_path)

                # Ensure the destination directory exists
                os.makedirs(os.path.dirname(dest_path), exist_ok=True)

                # if file exist, merge, else move
                if os.path.exists(dest_path):
                    # Merge images if destination file already exists
                    merge_images(dest_path, src_path, dest_path)
                else:
                    # Move the file if it does not exist
                    os.makedirs(os.path.dirname(dest_path), exist_ok=True)
                    shutil.move(src_path, dest_path)


def merge_tiles(config: dict, quiet: bool = True) -> None:
    """Merge tiles for a specific variable from individual models into a shared directory."""
    # Load the configuration file
    variable = config["variable"]["name"]
    scenario = config["cloud"]["scenario"]
    cycle = config["cloud"]["cycle"]
    s3_bucket = config["cloud"]["s3_bucket"]
    webviewer_folder = config["cloud"]["webviewer_folder"]

    # Initialize the cloud object
    cloud = Cloud(config)

    # tmp directories
    local_extract_path = "./tmp"
    shared_directory = "/output"

    # output
    output_s3_bucket = config["cloud"]["output_s3_bucket"]
    output_s3_prefix = webviewer_folder + "/{}/{}".format(scenario, cycle)

    # first make a list of all models within this scenario with the specific variable
    s3_keys = []
    for folder in cloud.list_folders(s3_bucket, "{}/models".format(scenario)):
        s3_key = (
            "{}/models/".format(scenario) + folder + "/tiles/{}.tgz".format(variable)
        )
        # check if the s3 key exists
        if cloud.check_file_exists(s3_bucket, s3_key):
            s3_keys.append(s3_key)

    # Ensure local directories exist and are empty
    shutil.rmtree(local_extract_path, ignore_errors=True)
    shutil.rmtree(shared_directory, ignore_errors=True)
    os.makedirs(local_extract_path, exist_ok=True)
    os.makedirs(shared_directory, exist_ok=True)

    # Download and extract each .tgz file
    for s3_key in s3_keys:
        print("s3key: ", s3_key)
        # create a tmp directory for each model and download
        tmp_dir = os.path.join(
            local_extract_path, os.path.splitext(os.path.basename(s3_key))[0]
        )
        print("tmp_dir: ", tmp_dir)
        try:
            cloud.download_and_extract_tgz(s3_bucket, s3_key, tmp_dir)
        except Exception as e:
            print("Failed to download and extract {}: {}".format(s3_key, e))
            continue
        if not quiet:
            print("Downloaded and extracted {}".format(s3_key))

        # Process the tiles (merge model tiles with existing tiles in shared directory)
        print("merging model tiles from " + tmp_dir + " to " + shared_directory)
        merge_model_tiles(tmp_dir, shared_directory)
        if not quiet:
            print("Processed tiles from {}".format(s3_key))

        # Clean up the extracted directory
        shutil.rmtree(tmp_dir)

    if not quiet:
        print("Merged tiles for variable {} in scenario {}".format(variable, scenario))

    # Upload the merged tiles back to S3
    # TODO parallelize this, e.g. using multithreading (maybe use bulkboto3?)
    cloud.upload_folder(
        output_s3_bucket, shared_directory, output_s3_prefix, quiet=quiet
    )
    # cloud.bulk_upload_folder(output_s3_bucket, shared_directory, output_s3_prefix, num_threads=8)


# Read config file (config.yml)
config = yaml2dict("config.yml")

print("Running merge_tiles.py")

merge_tiles(config, quiet=True)
