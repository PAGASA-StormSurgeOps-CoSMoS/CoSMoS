"""AWS S3 cloud storage operations for CoSMoS.

Provides upload, download, and file management functions for transferring
model input/output data between local storage and S3 buckets.
"""

import os
import pathlib
import tarfile
from multiprocessing.pool import ThreadPool
from typing import List

import boto3
import cht_utils.fileops as fo
from botocore.exceptions import ClientError

from .cosmos import cosmos


class Cloud:
    """Helper class for S3 cloud storage operations."""

    def __init__(self) -> None:
        """Create an S3 client from CoSMoS cloud configuration."""
        self.ready = True
        session = boto3.Session(
            aws_access_key_id=cosmos.config.cloud_config.access_key,
            aws_secret_access_key=cosmos.config.cloud_config.secret_key,
            region_name=cosmos.config.cloud_config.region,
        )
        self.s3_client = session.client("s3")

    def upload_file(
        self, bucket_name: str, file: str, s3_folder: str, quiet: bool = True
    ) -> None:
        """Upload a single file to S3.

        Parameters
        ----------
        bucket_name : str
            Target S3 bucket.
        file : str
            Local file path.
        s3_folder : str
            Destination folder key on S3.
        quiet : bool, optional
            Suppress progress messages.
        """
        s3_key = os.path.join(s3_folder, os.path.basename(file)).replace("\\", "/")
        self.s3_client.upload_file(file, bucket_name, s3_key)
        if not quiet:
            print(f"Uploaded {os.path.basename(file)}")

    def download_file(
        self,
        bucket_name: str,
        s3_folder: str,
        file: str,
        local_folder: str,
        quiet: bool = True,
    ) -> None:
        """Download a single file from S3.

        Parameters
        ----------
        bucket_name : str
            Source S3 bucket.
        s3_folder : str
            Source folder key on S3.
        file : str
            File name to download.
        local_folder : str
            Local destination folder.
        quiet : bool, optional
            Suppress progress messages.
        """
        s3_key = os.path.join(s3_folder, os.path.basename(file)).replace("\\", "/")
        local_path = os.path.join(local_folder, os.path.basename(file))
        self.s3_client.download_file(bucket_name, s3_key, local_path)
        if not quiet:
            print(f"Downloaded {os.path.basename(file)}")

    def delete_file(
        self, bucket_name: str, s3_folder: str, file: str, quiet: bool = True
    ) -> None:
        """Delete a single file from S3.

        Parameters
        ----------
        bucket_name : str
            S3 bucket name.
        s3_folder : str
            Folder key on S3.
        file : str
            File name to delete.
        quiet : bool, optional
            Suppress progress messages.
        """
        s3_key = os.path.join(s3_folder, os.path.basename(file)).replace("\\", "/")
        self.s3_client.delete_object(Bucket=bucket_name, Key=s3_key)
        if not quiet:
            print(f"Deleted {os.path.basename(file)}")

    def make_folder(self, bucket_name: str, s3_folder: str, quiet: bool = True) -> None:
        """Create a folder (empty key) on S3.

        Parameters
        ----------
        bucket_name : str
            S3 bucket name.
        s3_folder : str
            Folder key to create.
        quiet : bool, optional
            Suppress progress messages.
        """
        self.s3_client.put_objects(bBucket=bucket_name, Key=f"{s3_folder}/")
        if not quiet:
            print(f"Made folder: {s3_folder}")

    def upload_folder(
        self,
        bucket_name: str,
        local_folder: str,
        s3_folder: str,
        parallel: bool = True,
        quiet: bool = True,
    ) -> None:
        """Upload a local folder recursively to S3.

        Parameters
        ----------
        bucket_name : str
            Target S3 bucket.
        local_folder : str
            Local folder to upload.
        s3_folder : str
            Destination folder key on S3.
        parallel : bool, optional
            Use thread pool for parallel uploads.
        quiet : bool, optional
            Suppress progress messages.
        """
        local_folder = local_folder.replace("\\\\", "\\").replace("\\", "/")
        flist = _list_all_files(local_folder)
        if parallel:
            pool = ThreadPool()
            pool.starmap(
                _upload_single,
                [
                    (file, local_folder, s3_folder, bucket_name, self.s3_client, quiet)
                    for file in flist
                ],
            )
        else:
            for file in flist:
                _upload_single(
                    file, local_folder, s3_folder, bucket_name, self.s3_client, quiet
                )

    def download_folder(
        self, bucket_name: str, s3_folder: str, local_folder: str, quiet: bool = True
    ) -> None:
        """Download all files from an S3 folder to a local directory.

        Parameters
        ----------
        bucket_name : str
            Source S3 bucket.
        s3_folder : str
            Source folder key on S3.
        local_folder : str
            Local destination folder.
        quiet : bool, optional
            Suppress progress messages.
        """
        fo.mkdir(local_folder)
        objects = self.s3_client.list_objects(Bucket=bucket_name, Prefix=s3_folder)
        if "Contents" in objects:
            for obj in objects["Contents"]:
                s3_key = obj["Key"]
                local_path = os.path.join(local_folder, os.path.basename(s3_key))
                self.s3_client.download_file(bucket_name, s3_key, local_path)
                if not quiet:
                    print(f"Downloaded {os.path.basename(s3_key)}")

    def delete_folder(self, bucket_name: str, s3_folder: str) -> None:
        """Delete all objects under an S3 folder prefix.

        Parameters
        ----------
        bucket_name : str
            S3 bucket name.
        s3_folder : str
            Folder prefix to delete.
        """
        if not s3_folder.endswith("/"):
            s3_folder += "/"
        objects = self.s3_client.list_objects(Bucket=bucket_name, Prefix=s3_folder)
        if "Contents" in objects:
            for obj in objects["Contents"]:
                self.s3_client.delete_object(Bucket=bucket_name, Key=obj["Key"])

    def list_folders(self, bucket_name: str, s3_folder: str) -> List[str]:
        """List sub-folder names under an S3 prefix.

        Parameters
        ----------
        bucket_name : str
            S3 bucket name.
        s3_folder : str
            Parent folder prefix.

        Returns
        -------
        list of str
            Sub-folder names.
        """
        if not s3_folder.endswith("/"):
            s3_folder += "/"
        folders: List[str] = []
        paginator = self.s3_client.get_paginator("list_objects_v2")
        iterator = paginator.paginate(
            Bucket=bucket_name, Prefix=s3_folder, Delimiter="/"
        )
        for page in iterator:
            for subfolder in page.get("CommonPrefixes", []):
                subfolder_name = subfolder["Prefix"].rstrip("/").split("/")[-1]
                folders.append(subfolder_name)
        return folders

    def list_files(self, bucket_name: str, s3_folder: str) -> List[str]:
        """List all object keys under an S3 prefix.

        Parameters
        ----------
        bucket_name : str
            S3 bucket name.
        s3_folder : str
            Folder prefix to list.

        Returns
        -------
        list of str
            Full S3 keys of all objects.
        """
        paginator = self.s3_client.get_paginator("list_objects_v2")
        all_files: List[str] = []
        for page in paginator.paginate(Bucket=bucket_name, Prefix=s3_folder):
            if "Contents" in page:
                for obj in page["Contents"]:
                    all_files.append(obj["Key"])
        return all_files

    def download_and_extract_tgz(
        self, bucket_name: str, s3_folder: str, local_folder: str
    ) -> None:
        """Download and extract a ``.tgz`` archive from S3.

        Parameters
        ----------
        bucket_name : str
            S3 bucket name.
        s3_folder : str
            S3 key of the ``.tgz`` file.
        local_folder : str
            Local folder to extract into.
        """
        local_tgz_path = os.path.join("/tmp", os.path.basename(s3_folder))
        self.s3_client.download_file(bucket_name, s3_folder, local_tgz_path)
        with tarfile.open(local_tgz_path, "r:gz") as tar:
            tar.extractall(path=local_folder)
        os.remove(local_tgz_path)

    def check_file_exists(self, bucket_name: str, s3_key: str) -> bool:
        """Check whether an object exists on S3.

        Parameters
        ----------
        bucket_name : str
            S3 bucket name.
        s3_key : str
            Full S3 key to check.

        Returns
        -------
        bool
            ``True`` if the object exists.
        """
        try:
            self.s3_client.head_object(Bucket=bucket_name, Key=s3_key)
            return True
        except ClientError as e:
            if e.response["Error"]["Code"] == "404":
                return False
            raise

    def check_folder_exists(self, bucket_name: str, s3_key: str) -> bool:
        """Check whether a folder prefix exists on S3.

        Parameters
        ----------
        bucket_name : str
            S3 bucket name.
        s3_key : str
            Folder prefix to check.

        Returns
        -------
        bool
            ``True`` if the folder contains any sub-prefixes.
        """
        response = self.s3_client.list_objects_v2(
            Bucket=bucket_name, Prefix=s3_key, Delimiter="/"
        )
        return "CommonPrefixes" in response


def _list_all_files(src: str) -> List[str]:
    """Recursively list all files in a directory.

    Parameters
    ----------
    src : str
        Root directory to scan.

    Returns
    -------
    list of str
        Absolute paths of all files found.
    """
    return [str(f) for f in pathlib.Path(src).rglob("*") if f.is_file()]


def _upload_single(
    file: str,
    local_folder: str,
    s3_folder: str,
    bucket_name: str,
    s3_client: "boto3.client",
    quiet: bool,
) -> None:
    """Upload a single file as part of a folder upload.

    Parameters
    ----------
    file : str
        Local file path.
    local_folder : str
        Root local folder (stripped from the S3 key).
    s3_folder : str
        Destination folder key on S3.
    bucket_name : str
        Target S3 bucket.
    s3_client : boto3.client
        S3 client instance.
    quiet : bool
        Suppress progress messages.
    """
    relative = file.replace("\\", "/").replace(local_folder, "")
    s3_key = s3_folder + relative
    s3_client.upload_file(file, bucket_name, s3_key)
    if not quiet:
        print(f"Uploaded {file}")
