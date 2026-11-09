# -*- coding: utf-8 -*-
"""UrbanTransferBench: fixed-origin, 1 km² global equal-area grid for 9 cities.

Run INSIDE the QGIS Python console, not the system Python interpreter.
Edit ROOT once before running. Start with RUN_CITIES=['BJ'] for verification.

Protocol: EPSG:6933, 1000m x 1000m, global grid origin (0,0).
Full squares have 1,000,000 m² in projected coordinates; clipped polygons
record the actual intersection with city administrative territory.

This is a CUSTOM 1 km lattice in EPSG:6933, NOT the official NSIDC EASE-Grid
1km lattice (which has a different origin and nominal grid spacing).
"""

from pathlib import Path
import csv
import json
import math

from qgis.PyQt.QtCore import QVariant
from qgis.core import (
    QgsCoordinateReferenceSystem, QgsCoordinateTransform, QgsFeature,
    QgsFields, QgsField, QgsGeometry, QgsPointXY, QgsProject, QgsRectangle,
    QgsVectorFileWriter, QgsVectorLayer, QgsWkbTypes,
)

# ====================== USER SETTINGS ======================
ROOT = Path.home() / "li" / "城市区域"
INPUT_DIR = ROOT / "boundaries" / "raw_admin"
OUTPUT_DIR = ROOT / "grid_1km"

# First run with ['BJ']. Once outputs look correct, change to all nine codes.
RUN_CITIES = ["BJ"]
# RUN_CITIES = ["BJ", "CD", "SH", "SZ", "NYC", "CHI", "SF", "LON", "MAN"]

#CITY_CODES = ["BJ", "CD", "SH", "SZ", "NYC", "CHI", "SF", "LON", "MAN"]
CITY_CODES = ["BJ"]

CRS_CODE = "EPSG:6933"
CELL_M = 1000
ORIGIN_X = 0
ORIGIN_Y = 0
MIN_AREA_M2 = 1e-6  # strictly positive area, excluding point/line-only touches
# ===========================================================


def polygonal_geometry(geometry):
    """Return only polygon components as multipart polygon geometry."""
    if geometry is None or geometry.isNull() or geometry.isEmpty():
        return None
    if QgsWkbTypes.geometryType(geometry.wkbType()) == QgsWkbTypes.PolygonGeometry:
        result = QgsGeometry(geometry)
    else:
        parts = []
        for component in geometry.asGeometryCollection():
            if (not component.isNull() and not component.isEmpty() and
                    QgsWkbTypes.geometryType(component.wkbType()) == QgsWkbTypes.PolygonGeometry):
                parts.append(component)
        if not parts:
            return None
        result = QgsGeometry.unaryUnion(parts)
        if result.isNull() or result.isEmpty():
            return None
    if not result.isGeosValid():
        result = result.makeValid()
    if result.isNull() or result.isEmpty():
        return None
    if QgsWkbTypes.geometryType(result.wkbType()) != QgsWkbTypes.PolygonGeometry:
        # makeValid can create collections. Keep only their polygon components.
        parts = [p for p in result.asGeometryCollection()
                 if QgsWkbTypes.geometryType(p.wkbType()) == QgsWkbTypes.PolygonGeometry]
        if not parts:
            return None
        result = QgsGeometry.unaryUnion(parts)
    if not result.isMultipart():
        result.convertToMultiType()
    return result


def read_city_boundary(path, target_crs):
    layer = QgsVectorLayer(str(path), path.stem, "ogr")
    if not layer.isValid():
        raise RuntimeError(f"Could not open input: {path}")
    if not layer.crs().isValid():
        raise RuntimeError(f"Source CRS undefined: {path}. Assign correct source CRS before running.")
    transform = QgsCoordinateTransform(layer.crs(), target_crs, QgsProject.instance())
    components = []
    for f in layer.getFeatures():
        geom = polygonal_geometry(f.geometry())
        if geom is None:
            continue
        geom.transform(transform)
        if not geom.isGeosValid():
            geom = geom.makeValid()
        geom = polygonal_geometry(geom)
        if geom is not None:
            components.append(geom)
    if not components:
        raise RuntimeError(f"No valid polygon boundary in {path}")
    dissolved = QgsGeometry.unaryUnion(components)
    dissolved = polygonal_geometry(dissolved)
    if dissolved is None or dissolved.area() <= 0:
        raise RuntimeError(f"Failed to make a valid city boundary from {path}")
    return dissolved, layer.crs().authid(), layer.featureCount()


def make_fields():
    fields = QgsFields()
    for name, typ in [
        ("region_id", QVariant.String),
        ("city_id", QVariant.String),
        ("global_grid_id", QVariant.String),
        ("grid_row", QVariant.LongLong),
        ("grid_col", QVariant.LongLong),
        ("center_x", QVariant.Double),
        ("center_y", QVariant.Double),
        ("center_lon", QVariant.Double),
        ("center_lat", QVariant.Double),
        ("full_area_m2", QVariant.Double),
        ("area_in_city_m2", QVariant.Double),
        ("city_cover_ratio", QVariant.Double),
    ]:
        fields.append(QgsField(name, typ))
    return fields


def create_writer(path, fields, crs, layer_name):
    options = QgsVectorFileWriter.SaveVectorOptions()
    options.driverName = "GPKG"
    options.layerName = layer_name
    options.fileEncoding = "UTF-8"
    writer = QgsVectorFileWriter.create(
        str(path), fields, QgsWkbTypes.MultiPolygon, crs,
        QgsProject.instance().transformContext(), options
    )
    if writer is None or writer.hasError() != QgsVectorFileWriter.NoError:
        msg = "null writer" if writer is None else writer.errorMessage()
        raise RuntimeError(f"Cannot write {path}: {msg}")
    return writer


def add(writer, fields, geometry, attrs):
    f = QgsFeature(fields)
    f.setGeometry(geometry)
    f.setAttributes(attrs)
    if not writer.addFeature(f):
        raise RuntimeError("Unable to add grid feature to GeoPackage")


def validate_saved_grids(paths, expected_all, expected_full):
    """Read GeoPackages again: verify counts, identifiers and 1 km² full geometry."""
    full_ids = set()
    full_coords = set()
    clip_ids = set()
    results = {}
    for typ in ("all", "full", "clipped"):
        layer = QgsVectorLayer(str(paths[typ]), typ, "ogr")
        if not layer.isValid():
            raise RuntimeError(f"[QA] Cannot reopen {paths[typ]}")
        expected_count = expected_all if typ == "all" else expected_full
        if layer.featureCount() != expected_count:
            raise RuntimeError(f"[QA] {typ}: {layer.featureCount()} != {expected_count}")
        results[typ] = layer.featureCount()
        if typ == "full":
            for feature in layer.getFeatures():
                rid = feature["region_id"]
                coords = (int(feature["grid_row"]), int(feature["grid_col"]))
                if rid in full_ids or coords in full_coords:
                    raise RuntimeError(f"[QA] Duplicate id or coordinates in {typ}: {rid}, {coords}")
                full_ids.add(rid)
                full_coords.add(coords)
                if abs(feature.geometry().area() - 1_000_000) > 0.001:
                    raise RuntimeError(f"[QA] Nonstandard cell area in {typ}: {rid}")
        if typ == "clipped":
            for feature in layer.getFeatures():
                rid = feature["region_id"]
                if rid in clip_ids:
                    raise RuntimeError(f"[QA] Duplicate id in {typ}: {rid}")
                clip_ids.add(rid)
    if full_ids != clip_ids:
        raise RuntimeError("[QA] full and clipped region_id sets do not match")
    return results


def generate_city(city, target_crs, inverse_transform, fields):
    source = INPUT_DIR / f"{city}_boundary.gpkg"
    if not source.exists():
        raise FileNotFoundError(
            f"Missing {source}. Move the administrative city GeoPackage here first."
        )
    paths = {
        typ: OUTPUT_DIR / typ / f"{city}_grid_1km_{typ}.gpkg"
        for typ in ("all", "full", "clipped")
    }
    report_path = OUTPUT_DIR / "metadata" / f"{city}_grid_qa.json"
    exists = [p.exists() for p in list(paths.values()) + [report_path]]
    if all(exists):
        print(f"[{city}] Existing complete outputs detected, skipping (no overwrite).")
        return None
    if any(exists):
        raise FileExistsError(
            f"[{city}] Some existing output files found. Move them out of {OUTPUT_DIR} "
            "before regenerating; script will not overwrite data."
        )

    city_geom, source_crs, source_count = read_city_boundary(source, target_crs)
    bounds = city_geom.boundingBox()

    # 0,0-anchored, global integer-kilometre indices. DO NOT round per-city origin.
    col_start = math.floor((bounds.xMinimum() - ORIGIN_X) / CELL_M)
    col_stop = math.ceil((bounds.xMaximum() - ORIGIN_X) / CELL_M)
    row_start = math.floor((bounds.yMinimum() - ORIGIN_Y) / CELL_M)
    row_stop = math.ceil((bounds.yMaximum() - ORIGIN_Y) / CELL_M)
    if col_start >= col_stop or row_start >= row_stop:
        raise RuntimeError(f"Unusable boundary extent for {city}")

    # QGIS official API recommends prepared engine for large numbers of predicates.
    engine = QgsGeometry.createGeometryEngine(city_geom.constGet())
    engine.prepareGeometry()

    writers = {}
    try:
        for typ, path in paths.items():
            writers[typ] = create_writer(path, fields, target_crs, f"{city}_grid_1km_{typ}")

        n_all, n_full, area_sum, small_cells = 0, 0, 0.0, 0
        for row in range(row_start, row_stop):
            bottom = ORIGIN_Y + row * CELL_M
            top = bottom + CELL_M
            for col in range(col_start, col_stop):
                left = ORIGIN_X + col * CELL_M
                right = left + CELL_M
                full_geom = QgsGeometry.fromRect(QgsRectangle(left, bottom, right, top))
                # Writing a multipart GPKG geometry even for a single rectangle.
                full_geom.convertToMultiType()
                center_x, center_y = left + CELL_M / 2, bottom + CELL_M / 2
                lonlat = inverse_transform.transform(QgsPointXY(center_x, center_y))
                grid_uid = f"R{row}_C{col}"

                clipped_geom, actual_area = None, 0.0
                if engine.intersects(full_geom.constGet()):
                    clipped_geom = polygonal_geometry(city_geom.intersection(full_geom))
                    if clipped_geom is not None:
                        actual_area = clipped_geom.area()
                inside = actual_area > MIN_AREA_M2
                ratio = min(1.0, max(0.0, actual_area / (CELL_M * CELL_M)))
                region_id = f"{city}_{n_full + 1:06d}" if inside else None
                attrs = [region_id, city, grid_uid, row, col,
                         center_x, center_y, lonlat.x(), lonlat.y(),
                         float(CELL_M * CELL_M), actual_area, ratio]

                add(writers["all"], fields, full_geom, attrs)
                n_all += 1
                if inside:
                    add(writers["full"], fields, full_geom, attrs)
                    add(writers["clipped"], fields, clipped_geom, attrs)
                    n_full += 1
                    area_sum += actual_area
                    if ratio < 0.01:
                        small_cells += 1
            if (row - row_start + 1) % 20 == 0:
                print(f"[{city}] Processed {row - row_start + 1}/{row_stop - row_start} rows...")
    finally:
        # Closing writer handles is required to commit/finish GeoPackage files.
        for writer in writers.values():
            del writer
        writers.clear()

    saved_counts = validate_saved_grids(paths, n_all, n_full)
    boundary_area = city_geom.area()
    discrepancy = abs(area_sum - boundary_area) / boundary_area
    report = {
        "city_id": city,
        "input_file": str(source),
        "input_source_crs": source_crs,
        "input_polygon_feature_count": source_count,
        "grid_crs": CRS_CODE,
        "cell_size_projected_m": CELL_M,
        "fixed_global_origin_xy_m": [ORIGIN_X, ORIGIN_Y],
        "cols_global_index_half_open": [col_start, col_stop],
        "rows_global_index_half_open": [row_start, row_stop],
        "all_candidate_cells": n_all,
        "full_cells": n_full,
        "clipped_cells": saved_counts["clipped"],
        "saved_files_reopened_and_validated": True,
        "very_small_border_cells_ratio_below_0_01": small_cells,
        "boundary_area_m2": boundary_area,
        "sum_clipped_area_m2": area_sum,
        "relative_area_conservation_error": discrepancy,
        "unique_region_ids_expected": n_full,
        "unique_global_grid_ids_expected": n_full,
        "cells_are_unique_by_row_col_by_construction": True,
        "outputs": {k: str(v) for k, v in paths.items()},
        "warning": "Review whether the MAN boundary is Manchester City or Greater Manchester; these are different scopes."
                    if city == "MAN" else "",
    }
    with report_path.open("w", encoding="utf-8") as file:
        json.dump(report, file, ensure_ascii=False, indent=2)

    print(f"[{city}] all={n_all:,}, full=clipped={n_full:,}, relative area error={discrepancy:.3e}")
    if discrepancy > 1e-4:
        print(f"[{city}] WARNING: area conservation error above 0.01%: check boundary and intersection")
    return report


def main():
    invalid = set(RUN_CITIES) - set(CITY_CODES)
    if invalid:
        raise ValueError(f"Unknown city codes: {invalid}")
    target = QgsCoordinateReferenceSystem(CRS_CODE)
    if not target.isValid():
        raise RuntimeError(f"QGIS does not recognize {CRS_CODE}")
    for typ in ("all", "full", "clipped", "metadata"):
        (OUTPUT_DIR / typ).mkdir(parents=True, exist_ok=True)
    from_6933 = QgsCoordinateTransform(
        target, QgsCoordinateReferenceSystem("EPSG:4326"), QgsProject.instance()
    )
    fields = make_fields()
    definition_path = OUTPUT_DIR / "metadata" / "grid_definition.json"
    if not definition_path.exists():
        with definition_path.open("w", encoding="utf-8") as file:
            json.dump({
                "name": "UrbanTransferBench 1km custom fixed-origin equal-area grid",
                "projection": CRS_CODE,
                "grid_type": "projected rectangle polygon",
                "cell_width_m": CELL_M,
                "cell_height_m": CELL_M,
                "global_origin_x_m": ORIGIN_X,
                "global_origin_y_m": ORIGIN_Y,
                "keep_rule": "polygon intersection area > 1e-6 square metres",
                "row_col_formula": "floor((x - global_origin_x)/1000), floor((y - global_origin_y)/1000)",
                "model_geometry": "full",
                "area_summary_geometry": "clipped",
                "note": "This is a custom 1000 m lattice in EPSG:6933, not the official NSIDC 1 km EASE-Grid lattice.",
            }, file, ensure_ascii=False, indent=2)

    for city in RUN_CITIES:
        generate_city(city, target, from_6933, fields)

    # Build summary from validated output reports, including cities run previously.
    reports = []
    for city in CITY_CODES:
        p = OUTPUT_DIR / "metadata" / f"{city}_grid_qa.json"
        if p.exists():
            with p.open("r", encoding="utf-8") as file:
                reports.append(json.load(file))
    summary_csv = OUTPUT_DIR / "metadata" / "cities_grid_summary.csv"
    keys = ["city_id", "all_candidate_cells", "full_cells", "clipped_cells",
            "boundary_area_m2", "sum_clipped_area_m2", "relative_area_conservation_error"]
    with summary_csv.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=keys)
        writer.writeheader()
        for report in reports:
            writer.writerow({k: report[k] for k in keys})
    print("DONE. Output folder:", OUTPUT_DIR)
    print("Summary:", summary_csv)


main()
