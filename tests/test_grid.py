"""
Tests for House Grid Loader, Validator, and Dynamic Private Area Manager.
"""

from pathlib import Path
from device.grid import HouseGridLoader, HouseGrid, PrivateAreaManager
from device.storage import SecureStorage


def test_house_grid_loader():
    blueprint_path = Path(__file__).resolve().parent.parent / "data" / "house_grid.sample.json"
    grid = HouseGridLoader.load_from_file(blueprint_path)

    assert grid.rows == 8
    assert grid.columns == 10
    assert grid.cell_size_meters == 1.0

    # Test entrances and exits
    assert grid.is_entrance(7, 4) is True
    assert grid.is_exit(7, 4) is True
    assert grid.is_exit(0, 8) is True
    assert grid.is_entrance(0, 0) is False

    # Test zone lookup
    assert grid.get_zone(4, 2) == "Living Room"
    assert grid.get_zone(1, 2) == "Kitchen"
    assert grid.get_zone(4, 6) == "En-suite Bathroom"
    assert grid.get_zone(10, 10) == "Outside"


def test_private_area_manager(tmp_path: Path):
    db_file = tmp_path / "area_test.db"
    storage = SecureStorage(db_path=db_file)
    blueprint_path = Path(__file__).resolve().parent.parent / "data" / "house_grid.sample.json"
    grid = HouseGridLoader.load_from_file(blueprint_path)
    mgr = PrivateAreaManager(storage=storage, grid=grid)

    # Initially, Living Room is not marked private
    assert mgr.is_area_private(row=4, col=2, zone_name="Living Room") is False

    # Mark Living Room private via dashboard action
    mgr.set_zone_privacy("Living Room", is_private=True, set_by="caregiver")
    assert mgr.is_area_private(row=4, col=2, zone_name="Living Room") is True

    # Mark a specific cell in Kitchen as private (e.g. medicine drawer spot at (1, 2))
    assert mgr.is_area_private(row=1, col=2, zone_name="Kitchen") is False
    mgr.set_cell_privacy(1, 2, is_private=True, set_by="user")
    assert mgr.is_area_private(row=1, col=2, zone_name="Kitchen") is True
    # Other cells in Kitchen remain normal
    assert mgr.is_area_private(row=1, col=3, zone_name="Kitchen") is False

    # Verify persistence: New instance reloading from SQLite keeps settings
    mgr_reloaded = PrivateAreaManager(storage=storage, grid=grid)
    assert mgr_reloaded.is_area_private(row=4, col=2, zone_name="Living Room") is True
    assert mgr_reloaded.is_area_private(row=1, col=2, zone_name="Kitchen") is True
