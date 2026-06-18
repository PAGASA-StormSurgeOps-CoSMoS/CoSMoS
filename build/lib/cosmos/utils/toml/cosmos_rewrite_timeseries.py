"""Utility to rename and restructure time-series output files."""

import os


def rename_files1(directory: str) -> None:
    for filename in os.listdir(directory):
        # Check if the file matches the expected pattern
        if filename.startswith("waterlevel") and filename.endswith(".csv.js"):
            # Extract the number part (8760922 in this example)
            parts = filename.split(".")
            number = parts[2]
            model = parts[1]
            # Create the new filename
            new_filename = f"wl.{number}.{model}.csv.js"
            # Create full file paths
            old_file = os.path.join(directory, filename)
            new_file = os.path.join(directory, new_filename)
            # Rename the file
            os.rename(old_file, new_file)
            print(f"Renamed: {filename} to {new_filename}")


def rename_files2(directory: str) -> None:
    for filename in os.listdir(directory):
        # Check if the file matches the expected pattern
        if filename.startswith("wl") and filename.endswith(".js"):
            # Extract the number part (8760922 in this example)
            parts = filename.split(".")
            number = parts[1]
            model = parts[2]
            # Create the new filename
            new_filename = f"wl.{number}.{model}.csv.js"
            # Create full file paths
            old_file = os.path.join(directory, filename)
            new_file = os.path.join(directory, new_filename)
            # Rename the file
            os.rename(old_file, new_file)
            print(f"Renamed: {filename} to {new_filename}")


def rename_files_waves(directory: str) -> None:
    for filename in os.listdir(directory):
        # Check if the file matches the expected pattern
        if filename.startswith("waves") and filename.endswith(".csv.js"):
            # Extract the number part (8760922 in this example)
            parts = filename.split(".")
            number = parts[2]
            model = parts[1]

            if number.startswith("hurrywave"):
                print("Folder already renamed")
                return
            # Create the new filename
            new_filename = f"waves.{number}.{model}.csv.js"
            # Create full file paths
            old_file = os.path.join(directory, filename)
            new_file = os.path.join(directory, new_filename)
            # Rename the file
            os.rename(old_file, new_file)
            print(f"Renamed: {filename} to {new_filename}")


def rename_files_waves2(directory: str) -> None:
    for filename in os.listdir(directory):
        # Check if the file matches the expected pattern
        if filename.startswith("wl") and filename.endswith(".csv.js"):
            # Extract the number part (8760922 in this example)
            parts = filename.split(".")
            number = parts[1]
            model = parts[2]

            # if model conatain "hurrywave"
            if model.startswith("hurrywave"):
                # Create the new filename
                new_filename = f"waves.{number}.{model}.csv.js"
                # Create full file paths
                old_file = os.path.join(directory, filename)
                new_file = os.path.join(directory, new_filename)
                # Rename the file
                os.rename(old_file, new_file)
                print(f"Renamed: {filename} to {new_filename}")


# Example usage
ts_list = os.listdir(
    r"\\dfs-trusted.directory.intra\dfs\openearth-opendap-opendap\static\deltares\cosmos\nopp_event_viewer\data"
)
print(ts_list)

for ts in ts_list:
    directory_path = r"\\dfs-trusted.directory.intra\dfs\openearth-opendap-opendap\static\deltares\cosmos\nopp_event_viewer\data\{}\artificial_cycle\timeseries".format(
        ts
    )
    print(directory_path)
    rename_files_waves(directory_path)
