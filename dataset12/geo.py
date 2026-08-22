"""TVA bbox vs Power Service Area polygon on the Dataset 1 ERA5 1° grid."""
from __future__ import annotations

import json
import struct
from pathlib import Path

import numpy as np
from shapely import contains_xy
from shapely.geometry import Polygon, shape
from shapely.ops import unary_union

from .paths import TVA_EAST, TVA_GEOJSON, TVA_NORTH, TVA_SOUTH, TVA_WEST


def load_service_area(path: Path | None = None):
    path = Path(path or TVA_GEOJSON)
    geojson = json.loads(path.read_text())
    features = geojson.get("features") or [{"geometry": geojson.get("geometry")}]
    geoms = [shape(f["geometry"]) for f in features if f and f.get("geometry")]
    if not geoms:
        raise ValueError(f"No polygon in {path}")
    return unary_union(geoms)


def _read_shp_rings(shp_path: Path) -> list[list[list[tuple[float, float]]]]:
    data = Path(shp_path).read_bytes()
    offset = 100
    features: list[list[list[tuple[float, float]]]] = []
    while offset + 8 <= len(data):
        _rec, content_len = struct.unpack_from(">ii", data, offset)
        offset += 8
        nbytes = content_len * 2
        chunk = data[offset : offset + nbytes]
        offset += nbytes
        if len(chunk) < 44:
            continue
        stype = struct.unpack_from("<i", chunk, 0)[0]
        if stype != 5:
            continue
        nparts, npts = struct.unpack_from("<ii", chunk, 36)
        parts = list(struct.unpack_from(f"<{nparts}i", chunk, 44)) + [npts]
        pts_off = 44 + 4 * nparts
        xy = [struct.unpack_from("<dd", chunk, pts_off + i * 16) for i in range(npts)]
        rings = [xy[parts[i] : parts[i + 1]] for i in range(nparts)]
        features.append(rings)
    return features


def load_shapefile_lonlat(shp_path: Path):
    """Read Dataset 1 `tva_boundary.shp` (often UTM 16N) as lon/lat."""
    from pyproj import CRS, Transformer

    shp_path = Path(shp_path)
    prj = shp_path.with_suffix(".prj")
    crs = CRS.from_wkt(prj.read_text()) if prj.is_file() else CRS.from_epsg(4326)
    to_ll = Transformer.from_crs(crs, "EPSG:4326", always_xy=True)
    polys = []
    for rings in _read_shp_rings(shp_path):
        ll_rings = [
            list(zip(*to_ll.transform(*np.array(r).T))) for r in rings if len(r) >= 4
        ]
        if not ll_rings:
            continue
        shell, *holes = ll_rings
        poly = Polygon(shell, holes or None)
        if poly.is_valid:
            polys.append(poly)
        else:
            polys.append(poly.buffer(0))
    if not polys:
        raise ValueError(f"No polygons in {shp_path}")
    return unary_union(polys)


def bbox_mask(lat: np.ndarray, lon: np.ndarray) -> np.ndarray:
    lat2d, lon2d = np.meshgrid(lat, lon, indexing="ij")
    return (
        (lat2d >= TVA_SOUTH)
        & (lat2d <= TVA_NORTH)
        & (lon2d >= TVA_WEST)
        & (lon2d <= TVA_EAST)
    )


def polygon_mask(lat: np.ndarray, lon: np.ndarray, geom) -> np.ndarray:
    lon2d, lat2d = np.meshgrid(lon, lat)
    return np.asarray(contains_xy(geom, lon2d, lat2d))


def cell_mean(field: np.ndarray, mask: np.ndarray, lat: np.ndarray) -> float:
    if field.ndim == 3:
        field = np.nanmean(field, axis=0)
    weights = np.cos(np.deg2rad(lat))[:, None] * np.ones(field.shape)
    pick = mask & np.isfinite(field) & np.isfinite(weights)
    if not pick.any():
        return float("nan")
    w = weights[pick]
    return float(np.sum(field[pick] * w) / np.sum(w))


def exterior_xy(geom):
    """First exterior ring as (x, y) arrays, for overlay plots."""
    g = geom.geoms[0] if getattr(geom, "geom_type", "") == "MultiPolygon" else geom
    return np.asarray(g.exterior.xy[0]), np.asarray(g.exterior.xy[1])


# Aliases used by dataset1.py
load_service_area = load_service_area
bbox_mask = bbox_mask
polygon_mask = polygon_mask
cell_mean = cell_mean
load_shapefile_lonlat = load_shapefile_lonlat
exterior_xy = exterior_xy
