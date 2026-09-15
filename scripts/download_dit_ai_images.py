#!/usr/bin/env python3
"""Download images from dit_detect.ai_results.image into dit_photos/<source>/{result_id}.ext."""

from __future__ import annotations

import argparse
import logging
import sys
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import httpx
from psycopg2.extras import RealDictCursor

from collector.config import PROJECT_DIR
from collector.db import local_connection

logger = logging.getLogger(__name__)

WORKERS = 8
TIMEOUT = 60.0
RETRIES = 3
RETRY_STATUSES = {429, 500, 502, 503, 504}

_ROWS_SQL = """
SELECT result_id::text AS result_id, image, source_file
FROM dit_detect.ai_results
WHERE image IS NOT NULL AND btrim(image) <> ''
ORDER BY source_file, result_id
"""


@dataclass
class Stats:
    downloaded: int = 0
    skipped: int = 0
    failed: int = 0
    errors: list[str] = field(default_factory=list)


def _nfc(name: str) -> str:
    return unicodedata.normalize("NFC", name)


def _source_dir(source_file: str) -> str:
    stem = Path(_nfc(source_file)).stem
    return stem or "unknown"


def _extension_from_content_type(content_type: str | None) -> str:
    if not content_type:
        return ".jpg"
    lowered = content_type.split(";", 1)[0].strip().lower()
    if lowered == "image/png":
        return ".png"
    return ".jpg"


def _is_nonempty_file(path: Path) -> bool:
    try:
        return path.is_file() and path.stat().st_size > 0
    except OSError:
        return False


def _already_downloaded(dest_dir: Path, result_id: str) -> Path | None:
    for ext in (".jpg", ".jpeg", ".png"):
        path = dest_dir / f"{result_id}{ext}"
        if _is_nonempty_file(path):
            return path
    return None


def _unlink_quiet(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass


def _load_rows() -> list[dict]:
    with local_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(_ROWS_SQL)
            return list(cur.fetchall())


def _get_with_retries(client: httpx.Client, url: str) -> httpx.Response:
    last_exc: Exception | None = None
    for attempt in range(1, RETRIES + 1):
        try:
            resp = client.get(url, headers={"Accept": "image/jpeg, image/png"})
            if resp.status_code in RETRY_STATUSES:
                raise httpx.HTTPStatusError(
                    f"retryable status {resp.status_code}",
                    request=resp.request,
                    response=resp,
                )
            resp.raise_for_status()
            return resp
        except (httpx.HTTPError, OSError) as exc:
            last_exc = exc
            logger.warning("Attempt %s/%s failed for %s: %s", attempt, RETRIES, url, exc)
            if attempt < RETRIES:
                time.sleep(min(2 ** attempt, 8))
    assert last_exc is not None
    raise last_exc


def _download_one(
    client: httpx.Client,
    dest_root: Path,
    result_id: str,
    url: str,
    source_file: str,
) -> str:
    dest_dir = dest_root / _source_dir(source_file)
    existing = _already_downloaded(dest_dir, result_id)
    if existing is not None:
        return "skipped"

    dest_dir.mkdir(parents=True, exist_ok=True)
    part = dest_dir / f".{result_id}.part"
    try:
        resp = _get_with_retries(client, url)
        ext = _extension_from_content_type(resp.headers.get("content-type"))
        dest = dest_dir / f"{result_id}{ext}"
        part.write_bytes(resp.content)
        if part.stat().st_size == 0:
            raise ValueError(f"empty response body for {result_id}")
        part.replace(dest)
        return "downloaded"
    except Exception:
        _unlink_quiet(part)
        raise


def run(dest_root: Path, workers: int) -> Stats:
    dest_root.mkdir(parents=True, exist_ok=True)
    rows = _load_rows()
    stats = Stats()
    logger.info("Loaded %s row(s) from dit_detect.ai_results", len(rows))

    with httpx.Client(timeout=TIMEOUT, follow_redirects=True) as client:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {
                pool.submit(
                    _download_one,
                    client,
                    dest_root,
                    str(row["result_id"]).strip(),
                    str(row["image"]).strip(),
                    str(row["source_file"] or ""),
                ): row
                for row in rows
            }
            for future in as_completed(futures):
                row = futures[future]
                result_id = str(row["result_id"]).strip()
                try:
                    status = future.result()
                except Exception as exc:
                    stats.failed += 1
                    msg = f"{result_id}: {exc}"
                    stats.errors.append(msg)
                    logger.warning("Failed %s", msg)
                    continue
                if status == "skipped":
                    stats.skipped += 1
                else:
                    stats.downloaded += 1
                    if stats.downloaded % 200 == 0:
                        logger.info(
                            "Progress: downloaded=%s skipped=%s failed=%s",
                            stats.downloaded,
                            stats.skipped,
                            stats.failed,
                        )

    logger.info(
        "Done: downloaded=%s skipped=%s failed=%s total=%s",
        stats.downloaded,
        stats.skipped,
        stats.failed,
        len(rows),
    )
    for err in stats.errors[:20]:
        logger.info("  error: %s", err)
    if len(stats.errors) > 20:
        logger.info("  ... %s more error(s)", len(stats.errors) - 20)
    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dir",
        type=Path,
        default=PROJECT_DIR / "dit_photos",
        help="Output directory (default: PROJECT_DIR/dit_photos)",
    )
    parser.add_argument("--workers", type=int, default=WORKERS)
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    stats = run(args.dir.resolve(), max(1, args.workers))
    print(
        f"downloaded={stats.downloaded} skipped={stats.skipped} "
        f"failed={stats.failed}"
    )
    if stats.failed and stats.downloaded == 0 and stats.skipped == 0:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
