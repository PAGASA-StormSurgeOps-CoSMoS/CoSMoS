"""Utility to generate model grid outlines and topo-bathymetry tiles.

Creates index tiles, topography overlays, and spatial outlines from SFINCS
model grids for use in the CoSMoS web viewer.
"""

import os

# NOTE: make_topobathy_overlay was removed from cht_tiling.
# This script needs to be rewritten to use TiledWebMap or TopoBathyMap.
# from cht_tiling import make_topobathy_overlay
from cht_tiling.utils import get_zoom_level_for_resolution
from hydromt_sfincs import SfincsModel

# def interpolate_netcdf_onto_grid(dem_list, x, y, crs):
#     """Interpolate DEMs onto grid"""
#     # Interpolate DEMs onto grid
#     dem = np.zeros((len(y), len(x)))
#     dem_name = dem_list[0]
#     dem_file = dem_name
#     if not os.path.exists(dem_file):
#         print(f"DEM file {dem_file} not found")
#         return dem
#     with xr.open_dataset(dem_file) as ds:
#         # Get DEM data
#         lon = ds["lon"].values
#         lat = ds["lat"].values
#         z = ds["z"].values
#         # Interpolate onto grid
#         f = RegularGridInterpolator((lat, lon), z, method="linear")
#         dem[:, :] = f((y, x)).reshape((len(y), len(x)))
#     return dem


region = "us_west_coast_tsunami"
model_type = "sfincs"
# model_name  = "sfincs_us_west_coast_tsunami"
model_name = "sfincs_oregon_tsunami"
region_path = os.path.join("c:\\work\\cosmos\\model_database", region)
model_path = os.path.join(region_path, model_type, model_name)
input_path = os.path.join(model_path, "input")
misc_path = os.path.join(model_path, "misc")
tiling_path = os.path.join(model_path, "tiling")
index_path = os.path.join(tiling_path, "indices")
topo_path = os.path.join(tiling_path, "topobathy")

zoom_range = [0, 10]

# If misc_path does not exist, create it
if not os.path.exists(misc_path):
    os.makedirs(misc_path)

# If tiling_path does not exist, create it
if not os.path.exists(index_path):
    os.makedirs(index_path)

# If topo_path does not exist, create it
if not os.path.exists(topo_path):
    os.makedirs(topo_path)

sf = SfincsModel(root=input_path, mode="r")

# outline = sf.grid.get_exterior()
# geojson_file = os.path.join(misc_path, "outline.geojson")
# outline.to_file(geojson_file, driver="GeoJSON")

## Make index tiles
# make_index_tiles(sf.grid.data,
#                  index_path,
#                  zoom_range=zoom_range,
#                  format="png",
#                  webviewer=True)

# xl, yl = sf.grid.get_extent()

# # Make topobathy tiles
# make_topobathy_tiles(
#     topo_path,
#     dem_names=["gebco19"],
#     lon_range=xl,
#     lat_range=yl,
#     index_path=index_path,
#     zoom_range=zoom_range,
#     # z_range=None,
#     bathymetry_database_path="c:\\work\\delftdashboard\\data\\bathymetry",
#     quiet=False,
#     webviewer=True,
# )

izoom = get_zoom_level_for_resolution(400.0)
izoom = 4
compress_level = 9

topo_path = "c:\\work\\delftdashboard\\data\\bathymetry\\gebco2024"

# dem_file = "c:\\work\\data\\gebco_2024\\gebco_2024.nc"

# ds = xr.open_dataset(dem_file)

# # Make topobathy tiles (should send in a HydroMT function)
# make_topobathy_tiles_v2(
#     topo_path,
# #    dem_names=["gebco19"],
#     dataset=ds,
#     lon_range=[-180.0, 180.0],
#     lat_range=[-90.0, 90.0],
#     zoom_range=[0, izoom],
#     # z_range=None,
#     bathymetry_database_path="c:\\work\\delftdashboard\\data\\bathymetry",
#     quiet=False,
#     webviewer=True,
#     make_highest_level=True
# )


make_topobathy_overlay(
    topo_path,
    [-120.0, -100.0],
    [30.0, 50.0],
    npixels=800,
    # color_values=None,
    color_map="jet",
    color_range=[-10.0, 10.0],
    color_scale_auto=False,
    # color_scale_symmetric=True,
    color_scale_symmetric_side="min",
    hillshading=True,
    hillshading_azimuth=315,
    hillshading_altitude=30,
    hillshading_exaggeration=10.0,
    quiet=False,
    file_name="overlay.png",
)
