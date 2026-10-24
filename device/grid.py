"""
House Map Geo-Grid Loader, Validator, and Dynamic Private-Area Manager.
Loads house blueprint from JSON, validates schema and bounds, identifies entrance/exits,
and dynamically tracks private areas configured from the dashboard or local storage.
"""

from __future__ import annotations
import json
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple, Any

from device.config import config
from device.models import PrivateAreaSetting
from device.storage import SecureStorage


class HouseGrid:
    def __init__(self, blueprint_data: Dict[str, Any]):
        self.raw_data = blueprint_data
        self.version = blueprint_data.get("version", "1.0")
        self.name = blueprint_data.get("name", "Unnamed Residence")
        self.description = blueprint_data.get("description", "")

        dims = blueprint_data.get("dimensions", {})
        self.rows: int = dims.get("rows", 8)
        self.columns: int = dims.get("columns", 10)
        self.cell_size_meters: float = dims.get("cell_size_meters", 1.0)

        # Entrance and exit coordinates
        self.entrances: Set[Tuple[int, int]] = {
            (entry["row"], entry["col"]) for entry in blueprint_data.get("entrances", [])
        }
        self.exits: Set[Tuple[int, int]] = {
            (exit_pt["row"], exit_pt["col"]) for exit_pt in blueprint_data.get("exits", [])
        }

        # Zones mapping
        self.named_zones: List[Dict[str, Any]] = blueprint_data.get("named_zones", [])
        self.cell_to_zone: Dict[Tuple[int, int], str] = {}
        self.zone_to_cells: Dict[str, List[Tuple[int, int]]] = {}

        for zone in self.named_zones:
            z_name = zone["name"]
            self.zone_to_cells[z_name] = []
            for cell in zone.get("cells", []):
                pt = (cell["row"], cell["col"])
                self.cell_to_zone[pt] = z_name
                self.zone_to_cells[z_name].append(pt)

        # Walls list
        self.walls = blueprint_data.get("walls", [])

    def is_valid_cell(self, row: int, col: int) -> bool:
        return 0 <= row < self.rows and 0 <= col < self.columns

    def get_zone(self, row: int, col: int) -> str:
        if not self.is_valid_cell(row, col):
            return "Outside"
        return self.cell_to_zone.get((row, col), "General Hallway")

    def is_entrance(self, row: int, col: int) -> bool:
        return (row, col) in self.entrances

    def is_exit(self, row: int, col: int) -> bool:
        return (row, col) in self.exits


class HouseGridLoader:
    @staticmethod
    def load_from_file(file_path: Optional[Path] = None) -> HouseGrid:
        path = file_path or config.BLUEPRINT_FILE
        if not path.exists():
            raise FileNotFoundError(f"Blueprint file not found at: {path}")

        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        HouseGridLoader.validate_blueprint(data)
        return HouseGrid(data)

    @staticmethod
    def validate_blueprint(data: Dict[str, Any]):
        """Ensure structural integrity of blueprint."""
        if "dimensions" not in data:
            raise ValueError("Blueprint missing 'dimensions' block.")
        dims = data["dimensions"]
        if dims.get("rows", 0) <= 0 or dims.get("columns", 0) <= 0:
            raise ValueError("Grid rows and columns must be greater than 0.")

        if not data.get("entrances"):
            raise ValueError("Blueprint must contain at least one marked entrance.")
        if not data.get("exits"):
            raise ValueError("Blueprint must contain at least one marked exit.")

        rows, cols = dims["rows"], dims["columns"]
        for entry in data["entrances"]:
            r, c = entry.get("row", -1), entry.get("col", -1)
            if not (0 <= r < rows and 0 <= c < cols):
                raise ValueError(f"Entrance coordinate ({r}, {c}) is outside grid bounds.")

        for exit_pt in data["exits"]:
            r, c = exit_pt.get("row", -1), exit_pt.get("col", -1)
            if not (0 <= r < rows and 0 <= c < cols):
                raise ValueError(f"Exit coordinate ({r}, {c}) is outside grid bounds.")


class PrivateAreaManager:
    """
    Manages private room and cell configurations.
    Which areas are private is NOT fixed in the blueprint file:
    people choose it in the dashboard, stored in SQLite with cloud as master copy.
    """

    def __init__(self, storage: SecureStorage, grid: HouseGrid):
        self.storage = storage
        self.grid = grid
        # In-memory caches for zero-latency lookup
        self.private_zones: Set[str] = set()
        self.private_cells: Set[Tuple[int, int]] = set()
        self.reload_from_storage()

    def reload_from_storage(self):
        settings = self.storage.get_private_area_settings()
        self.private_zones.clear()
        self.private_cells.clear()

        for s in settings:
            if s.is_private:
                if s.zone_name:
                    self.private_zones.add(s.zone_name)
                if s.cell_row is not None and s.cell_col is not None:
                    self.private_cells.add((s.cell_row, s.cell_col))
            else:
                if s.zone_name and s.zone_name in self.private_zones:
                    self.private_zones.remove(s.zone_name)
                if (
                    s.cell_row is not None
                    and s.cell_col is not None
                    and (s.cell_row, s.cell_col) in self.private_cells
                ):
                    self.private_cells.remove((s.cell_row, s.cell_col))

    def set_zone_privacy(self, zone_name: str, is_private: bool, set_by: str = "caregiver"):
        setting = PrivateAreaSetting(
            zone_name=zone_name,
            cell_row=None,
            cell_col=None,
            is_private=is_private,
            set_by=set_by,
        )
        self.storage.save_private_area_setting(setting)
        if is_private:
            self.private_zones.add(zone_name)
        else:
            self.private_zones.discard(zone_name)

    def set_cell_privacy(self, row: int, col: int, is_private: bool, set_by: str = "user"):
        setting = PrivateAreaSetting(
            zone_name=None,
            cell_row=row,
            cell_col=col,
            is_private=is_private,
            set_by=set_by,
        )
        self.storage.save_private_area_setting(setting)
        if is_private:
            self.private_cells.add((row, col))
        else:
            self.private_cells.discard((row, col))

    def is_area_private(self, row: Optional[int], col: Optional[int], zone_name: Optional[str] = None) -> bool:
        """
        Check if given coordinate or zone is private.
        Cell-specific override takes precedence, then zone-level privacy.
        """
        if row is not None and col is not None:
            if (row, col) in self.private_cells:
                return True
            resolved_zone = zone_name or self.grid.get_zone(row, col)
            if resolved_zone in self.private_zones:
                return True
            return False

        if zone_name and zone_name in self.private_zones:
            return True

        return False
