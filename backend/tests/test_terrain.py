"""Unit tests for TerrainService."""
from pathlib import Path

from app.services.terrain_service import TerrainService


def test_elevation_extraction_for_known_spot():
    service = TerrainService()
    # Silk Board Junction
    res = service.get_elevation(12.9177, 77.6233)
    assert res.status == "available"
    assert res.elevation_m is not None
    assert round(res.elevation_m, 1) == 898.0


def test_invalid_coordinates_handled_safely():
    service = TerrainService()
    # Invalid latitude > 90
    res = service.get_elevation(95.0, 77.6233)
    assert res.status == "out_of_bounds"
    assert res.elevation_m is None

    # Invalid longitude < -180
    res = service.get_elevation(12.9177, -190.0)
    assert res.status == "out_of_bounds"
    assert res.elevation_m is None


def test_out_of_study_bounds_returns_out_of_bounds():
    service = TerrainService()
    # Mumbai coordinates (outside Bengaluru bounding box)
    res = service.get_elevation(19.0760, 72.8777)
    assert res.status == "out_of_bounds"
    assert res.elevation_m is None


def test_missing_tile_returns_clean_missing_tile_status(tmp_path: Path):
    # Empty directory with no DEM tiles
    empty_service = TerrainService(dem_dir=tmp_path)
    res = empty_service.get_elevation(12.9500, 77.6000)
    assert res.status == "missing_tile"
    assert res.elevation_m is None
    assert "No DEM elevation tile" in res.message


def test_missing_dem_dir_returns_unavailable(tmp_path: Path):
    non_existent = tmp_path / "does_not_exist"
    service = TerrainService(dem_dir=non_existent)
    res = service.get_elevation(12.9500, 77.6000)
    assert res.status == "unavailable"
    assert res.elevation_m is None


def test_slope_calculation():
    service = TerrainService()
    # Silk Board has local neighbor offsets in bengaluru_dem_sample.json
    res = service.get_elevation(12.9177, 77.6233)
    assert res.status == "available"
    assert res.slope_pct is not None
    assert res.slope_pct >= 0.0

