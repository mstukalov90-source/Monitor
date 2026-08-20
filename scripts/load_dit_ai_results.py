#!/usr/bin/env python3
"""Load fivegen DIT JSON dumps into dit_detect.ai_results."""

from __future__ import annotations

import argparse
import json
import logging
import sys
import unicodedata
from pathlib import Path
from typing import Any, Iterable

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from psycopg2.extras import execute_values

from collector.config import PROJECT_DIR
from collector.db import local_connection

logger = logging.getLogger(__name__)

SOURCE_FILES = (
    "Навалы_1_половина_августа_МГГТ.json",
    "Стройки_1_половина_августа_МГГТ.json",
    "Стройки_КИНС_август_14_08_МГГТ.json",
)

INSERT_SQL = """
INSERT INTO dit_detect.ai_results (
    result_id,
    origin_screenshot_id,
    device,
    camera,
    create_timestamp,
    created_at,
    image,
    image_type,
    issues,
    latitude,
    longitude,
    geom,
    angle,
    speed,
    valid,
    height,
    ptz_position,
    source_file,
    provider
) VALUES %s
ON CONFLICT (result_id) DO UPDATE SET
    origin_screenshot_id = EXCLUDED.origin_screenshot_id,
    device = EXCLUDED.device,
    camera = EXCLUDED.camera,
    create_timestamp = EXCLUDED.create_timestamp,
    created_at = EXCLUDED.created_at,
    image = EXCLUDED.image,
    image_type = EXCLUDED.image_type,
    issues = EXCLUDED.issues,
    latitude = EXCLUDED.latitude,
    longitude = EXCLUDED.longitude,
    geom = EXCLUDED.geom,
    angle = EXCLUDED.angle,
    speed = EXCLUDED.speed,
    valid = EXCLUDED.valid,
    height = EXCLUDED.height,
    ptz_position = EXCLUDED.ptz_position,
    source_file = EXCLUDED.source_file,
    provider = EXCLUDED.provider,
    loaded_at = NOW()
"""

ROW_TEMPLATE = """(
    %s::uuid,
    %s::uuid,
    %s::uuid,
    %s::uuid,
    %s,
    to_timestamp(%s),
    %s,
    %s,
    %s::jsonb,
    %s,
    %s,
    CASE
        WHEN %s IS NULL OR %s IS NULL THEN NULL
        ELSE ST_SetSRID(ST_MakePoint(%s, %s), 4326)
    END,
    %s,
    %s,
    %s,
    %s,
    %s::jsonb,
    %s,
    %s
)
"""


def _nfc(name: str) -> str:
    return unicodedata.normalize("NFC", name)


def _index_json_files(directory: Path) -> dict[str, Path]:
    indexed: dict[str, Path] = {}
    for path in directory.iterdir():
        if path.suffix.lower() != ".json" or not path.is_file():
            continue
        indexed[_nfc(path.name)] = path
    return indexed


def _resolve_sources(directory: Path) -> list[tuple[str, Path]]:
    indexed = _index_json_files(directory)
    resolved: list[tuple[str, Path]] = []
    missing: list[str] = []
    for expected in SOURCE_FILES:
        key = _nfc(expected)
        path = indexed.get(key)
        if path is None:
            missing.append(expected)
            continue
        resolved.append((expected, path))
    if missing:
        available = ", ".join(sorted(indexed)) or "(none)"
        raise FileNotFoundError(
            f"Missing JSON in {directory}: {', '.join(missing)}. Available: {available}"
        )
    return resolved


def _optional_uuid(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _row(result: dict[str, Any], *, source_file: str, provider: str | None) -> tuple:
    lat = result.get("latitude")
    lon = result.get("longitude")
    create_ts = result.get("create_timestamp")
    issues = result.get("issues") or []
    ptz = result.get("ptz_position")
    return (
        result["id"],
        _optional_uuid(result.get("origin_screenshot_id")),
        _optional_uuid(result.get("device")),
        _optional_uuid(result.get("camera")),
        create_ts,
        create_ts,
        result.get("image"),
        result.get("image_type"),
        json.dumps(issues, ensure_ascii=False),
        lat,
        lon,
        lon,
        lat,
        lon,
        lat,
        result.get("angle"),
        result.get("speed"),
        result.get("valid"),
        result.get("height"),
        json.dumps(ptz, ensure_ascii=False) if ptz is not None else None,
        source_file,
        provider,
    )


def _load_file(path: Path, source_file: str) -> tuple[str | None, list[tuple]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path.name}: expected object with results[]")
    provider = payload.get("provider")
    results = payload.get("results")
    if not isinstance(results, list):
        raise ValueError(f"{path.name}: missing results array")
    rows = [_row(item, source_file=source_file, provider=provider) for item in results]
    return provider, rows


def _upsert(rows: Iterable[tuple], *, page_size: int = 500) -> int:
    batch = list(rows)
    if not batch:
        return 0
    with local_connection() as conn:
        with conn.cursor() as cur:
            execute_values(
                cur,
                INSERT_SQL,
                batch,
                template=ROW_TEMPLATE,
                page_size=page_size,
            )
    return len(batch)


def _verify() -> tuple[int, list[tuple[str, int]]]:
    with local_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM dit_detect.ai_results")
            total = int(cur.fetchone()[0])
            cur.execute(
                """
                SELECT source_file, COUNT(*)
                FROM dit_detect.ai_results
                GROUP BY source_file
                ORDER BY source_file
                """
            )
            by_file = [(row[0], int(row[1])) for row in cur.fetchall()]
    return total, by_file


def run(directory: Path) -> None:
    sources = _resolve_sources(directory)
    loaded = 0
    for source_file, path in sources:
        logger.info("Loading %s from %s", source_file, path)
        _, rows = _load_file(path, source_file)
        n = _upsert(rows)
        loaded += n
        logger.info("Upserted %s row(s) from %s", n, source_file)

    total, by_file = _verify()
    logger.info("Processed %s JSON row(s); table count=%s", loaded, total)
    for name, count in by_file:
        logger.info("  %s: %s", name, count)
    print(f"processed={loaded} table_count={total}")
    for name, count in by_file:
        print(f"{name}\t{count}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dir",
        type=Path,
        default=PROJECT_DIR / "dit_json",
        help="Directory with DIT JSON dumps (default: PROJECT_DIR/dit_json)",
    )
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    run(args.dir.resolve())


if __name__ == "__main__":
    main()
