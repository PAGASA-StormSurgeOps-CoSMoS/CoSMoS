"""Observation station management for CoSMoS.

Reads, stores, and provides access to tide gauge and wave buoy observation
stations used for model validation and data assimilation.
"""

import os
from typing import Dict, List, Optional

import toml
from cht_utils import fileops as fo


class Station:
    """Single observation station with location and metadata."""

    def __init__(self) -> None:
        """Initialize station with default attribute values."""
        self.name: Optional[str] = None
        self.coops_id: Optional[str] = None
        self.ndbc_id: Optional[str] = None
        self.iho_id: Optional[str] = None
        self.id: Optional[str] = None
        self.long_name: Optional[str] = None
        self.longitude: Optional[float] = None
        self.latitude: Optional[float] = None
        self.type: Optional[str] = None
        self.mllw: Optional[float] = None
        self.water_level_correction: float = 0.0
        self.file_name: Optional[str] = None
        self.upload: bool = True
        self.hat: Optional[float] = None
        self.x: Optional[float] = None
        self.y: Optional[float] = None


class Stations:
    """Collection of observation station sets.

    Each station set is read from a separate TOML file and keyed by name
    (e.g. ``"iho"``, ``"coops"``).
    """

    def __init__(self) -> None:
        """Initialize empty station collection."""
        self.station: List[Station] = []
        self.station_set: Dict[str, List[Station]] = {}

    def read_all(self) -> None:
        """Read all station sets from TOML files in the stations folder."""
        from .cosmos import cosmos

        file_list = fo.list_files(os.path.join(cosmos.config.path.stations, "*.toml"))
        for file_name in file_list:
            station_set_name = os.path.basename(file_name).replace(".toml", "")
            self.station_set[station_set_name] = read_station_set(file_name)

    def find_by_name(self, name: str) -> Optional[Station]:
        """Find a station by name across all station sets.

        Parameters
        ----------
        name : str
            Station name to search for (case-insensitive).

        Returns
        -------
        Station or None
            Matching station, or ``None`` if not found.
        """
        for station_set in self.station_set.values():
            for station in station_set:
                if station.name.lower() == name:
                    return station
        return None


def read_station_set(file_name: str) -> List[Station]:
    """Read a station set from a TOML file.

    Parameters
    ----------
    file_name : str
        Path to the TOML file containing station definitions.

    Returns
    -------
    list of Station
        Parsed station objects.
    """
    toml_dict = toml.load(file_name)
    station_list: List[Station] = []

    for toml_stat in toml_dict["station"]:
        station = Station()
        station.name = toml_stat["name"]
        if "longname" in toml_stat:
            station.long_name = toml_stat["longname"]
        elif "long_name" in toml_stat:
            station.long_name = toml_stat["long_name"]
        else:
            station.long_name = toml_stat["name"]
        station.longitude = toml_stat["longitude"]
        station.latitude = toml_stat["latitude"]
        station.type = toml_stat["type"]
        if "water_level_correction" in toml_stat:
            station.water_level_correction = toml_stat["water_level_correction"]
        if "MLLW" in toml_stat:
            station.mllw = toml_stat["MLLW"]
        if "coops_id" in toml_stat:
            station.coops_id = toml_stat["coops_id"]
            station.id = toml_stat["coops_id"]
        if "iho_id" in toml_stat:
            station.iho_id = toml_stat["iho_id"]
            station.id = toml_stat["iho_id"]
        if "ndbc_id" in toml_stat:
            station.ndbc_id = toml_stat["ndbc_id"]
            station.id = toml_stat["ndbc_id"]
        if "id" in toml_stat:
            station.id = toml_stat["id"]
        if "hat" in toml_stat:
            station.hat = toml_stat["hat"]

        station.file_name = os.path.basename(file_name)
        station_list.append(station)

    return station_list
