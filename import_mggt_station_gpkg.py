#!/usr/bin/env python3
"""CLI: import КГС.gpkg and СПС GeoPackage into mggt_station tables (WGS84)."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from collector.config import PROJECT_DIR
from collector.mggt_station_import import import_gpkg_files

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

DEFAULT_KGS = PROJECT_DIR / "КГС.gpkg"
DEFAULT_SPS = PROJECT_DIR / "СПС - ЮТ - Беговой.gpkg"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Import KGS/SPS GeoPackage files into mggt_station (EPSG:4326)",
    )
    parser.add_argument(
        "--kgs",
        type=Path,
        default=DEFAULT_KGS,
        help=f"Path to КГС GeoPackage (default: {DEFAULT_KGS.name})",
    )
    parser.add_argument(
        "--sps",
        type=Path,
        default=DEFAULT_SPS,
        help=f"Path to СПС GeoPackage (default: {DEFAULT_SPS.name})",
    )
    parser.add_argument(
        "--no-truncate",
        action="store_true",
        help="Append rows instead of truncating target tables first",
    )
    parser.add_argument(
        "--no-migrate",
        action="store_true",
        help="Skip applying sql/26 migration before import",
    )
    args = parser.parse_args()

    try:
        result = import_gpkg_files(
            args.kgs.resolve(),
            args.sps.resolve(),
            truncate=not args.no_truncate,
            apply_migration=not args.no_migrate,
        )
    except Exception as exc:
        logger.error("%s", exc)
        return 1

    print("\nImport summary:")
    for item in result.tables:
        print(f"  mggt_station.{item.table}: {item.loaded} rows")
    print(f"  skipped (no geometry): {result.skipped_no_geometry}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
