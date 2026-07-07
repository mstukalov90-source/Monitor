#!/usr/bin/env python3
"""Audit data_mos split tables vs crm.tasks linkage."""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import psycopg2

from collector.config import LOCAL_DB
from collector.crm_task_sync_config import SERVICE_TASK_SYNC

LAYERS = ("points", "lines", "polygons")
PREFIXES = {"points": "point", "lines": "line", "polygons": "polygon"}


@dataclass
class SplitRow:
    service: str
    layer: str
    total: int
    with_geom: int
    linked: int
    gap: int
    crm_match: int
    would_insert: int


def _conn():
    return psycopg2.connect(
        host=LOCAL_DB["host"],
        port=LOCAL_DB["port"],
        dbname=LOCAL_DB["dbname"],
        user=LOCAL_DB["user"],
        password=LOCAL_DB["password"],
        connect_timeout=30,
    )


def collect_split_rows(cur) -> list[SplitRow]:
    rows: list[SplitRow] = []
    for svc_name, cfg in SERVICE_TASK_SYNC.items():
        col = cfg.task_column
        for layer in LAYERS:
            tbl = f"data_mos.{svc_name}_{layer}"
            prefix = PREFIXES[layer]
            cur.execute(
                f"""
                SELECT
                  count(*) AS total,
                  count(*) FILTER (WHERE geom IS NOT NULL) AS with_geom,
                  count(*) FILTER (WHERE task_key IS NOT NULL) AS linked,
                  count(*) FILTER (WHERE geom IS NOT NULL AND task_key IS NULL) AS gap,
                  count(*) FILTER (
                    WHERE geom IS NOT NULL AND task_key IS NULL
                      AND EXISTS (
                        SELECT 1 FROM crm.tasks ct
                        WHERE ct."{col}" = CONCAT('{prefix}:', t.id::text)
                      )
                  ) AS crm_exists_not_linked,
                  count(*) FILTER (
                    WHERE geom IS NOT NULL AND task_key IS NULL
                      AND NOT EXISTS (
                        SELECT 1 FROM crm.tasks ct
                        WHERE ct."{col}" = CONCAT('{prefix}:', t.id::text)
                      )
                  ) AS would_insert
                FROM {tbl} t
                """
            )
            total, with_geom, linked, gap, crm_nl, would_ins = cur.fetchone()
            rows.append(
                SplitRow(
                    service=svc_name,
                    layer=layer,
                    total=int(total),
                    with_geom=int(with_geom),
                    linked=int(linked),
                    gap=int(gap),
                    crm_match=int(linked) + int(crm_nl),
                    would_insert=int(would_ins),
                )
            )
    return rows


def collect_false_tasked(cur) -> dict[str, int]:
    out: dict[str, int] = {}
    for svc_name in SERVICE_TASK_SYNC:
        parent = f"data_mos.{svc_name}"
        cur.execute(
            f"""
            SELECT count(*) FROM {parent} p
            WHERE p.tasked IS TRUE AND NOT EXISTS (
                SELECT 1 FROM {parent}_points c
                WHERE c.source_id = p.id AND c.task_key IS NOT NULL
                UNION ALL
                SELECT 1 FROM {parent}_lines c
                WHERE c.source_id = p.id AND c.task_key IS NOT NULL
                UNION ALL
                SELECT 1 FROM {parent}_polygons c
                WHERE c.source_id = p.id AND c.task_key IS NOT NULL
            )
            """
        )
        out[svc_name] = int(cur.fetchone()[0])
    return out


def collect_crm_scoped(cur) -> dict[str, dict[str, int]]:
    out: dict[str, dict[str, int]] = {}
    for svc_name, cfg in SERVICE_TASK_SYNC.items():
        col = cfg.task_column
        counts: dict[str, int] = {}
        total = 0
        for prefix in ("point", "line", "polygon"):
            cur.execute(
                f'SELECT count(*) FROM crm.tasks WHERE "{col}" LIKE %s',
                (f"{prefix}:%",),
            )
            counts[prefix] = int(cur.fetchone()[0])
            total += counts[prefix]
        counts["total"] = total
        out[col] = counts
    return out


def collect_duplicate_task_keys(cur) -> list[tuple[str, str, int]]:
    dups: list[tuple[str, str, int]] = []
    for svc_name in SERVICE_TASK_SYNC:
        for layer in LAYERS:
            tbl = f"data_mos.{svc_name}_{layer}"
            cur.execute(
                f"""
                SELECT task_key::text, count(*) FROM {tbl}
                WHERE task_key IS NOT NULL
                GROUP BY 1 HAVING count(*) > 1
                """
            )
            for task_key, cnt in cur.fetchall():
                dups.append((tbl, task_key, int(cnt)))
    return dups


def collect_multi_match_restore_candidates(cur) -> list[tuple[str, int, int]]:
    """Rows sharing global_id + geom_hash (restore collision risk)."""
    hits: list[tuple[str, int, int]] = []
    for svc_name in SERVICE_TASK_SYNC:
        for layer in LAYERS:
            tbl = f"data_mos.{svc_name}_{layer}"
            cur.execute(
                f"""
                SELECT global_id, count(*) AS cnt
                FROM {tbl}
                WHERE global_id IS NOT NULL AND geom IS NOT NULL
                GROUP BY global_id, md5(ST_AsEWKB(ST_SetSRID(ST_MakeValid(geom), 4326)))
                HAVING count(*) > 1
                ORDER BY cnt DESC
                LIMIT 5
                """
            )
            for global_id, cnt in cur.fetchall():
                hits.append((tbl, int(global_id), int(cnt)))
    return hits


def collect_recent_job_runs(cur, limit: int = 10) -> list[tuple]:
    cur.execute(
        """
        SELECT job_name, status, finished_at, left(message, 200)
        FROM collector.job_runs
        WHERE job_name IN (
            'data_mos_2855', 'data_mos_62501', 'data_mos_62441', 'data_mos_62461'
        )
        ORDER BY finished_at DESC NULLS LAST
        LIMIT %s
        """,
        (limit,),
    )
    return cur.fetchall()


def render_report(
    *,
    title: str,
    split_rows: list[SplitRow],
    false_tasked: dict[str, int],
    crm_scoped: dict[str, dict[str, int]],
    duplicate_keys: list[tuple[str, str, int]],
    multi_match: list[tuple[str, int, int]],
    job_runs: list[tuple],
) -> str:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    total_geom = sum(r.with_geom for r in split_rows)
    total_linked = sum(r.linked for r in split_rows)
    total_gap = sum(r.gap for r in split_rows)
    pct = (100.0 * total_linked / total_geom) if total_geom else 0.0

    lines = [
        f"# {title}",
        "",
        f"Generated: {ts}",
        "",
        "## Summary",
        "",
        f"- Split rows with geom: **{total_geom}**",
        f"- Linked (`task_key` set): **{total_linked}** ({pct:.1f}%)",
        f"- Gap (geom without `task_key`): **{total_gap}**",
        f"- False `tasked` parents: **{sum(false_tasked.values())}**",
        f"- Duplicate `task_key` in split tables: **{len(duplicate_keys)}**",
        "",
        "## Split tables",
        "",
        "| service | layer | total | geom | linked | gap | crm_match | would_insert |",
        "|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    for r in split_rows:
        lines.append(
            f"| {r.service} | {r.layer} | {r.total} | {r.with_geom} | "
            f"{r.linked} | {r.gap} | {r.crm_match} | {r.would_insert} |"
        )

    lines.extend(["", "## False tasked parents", ""])
    for svc, cnt in false_tasked.items():
        lines.append(f"- `{svc}`: **{cnt}**")

    lines.extend(["", "## CRM scoped tasks (point/line/polygon)", ""])
    for col, counts in crm_scoped.items():
        lines.append(
            f"- `{col}`: point={counts['point']}, line={counts['line']}, "
            f"polygon={counts['polygon']}, total={counts['total']}"
        )

    lines.extend(["", "## Duplicate task_key", ""])
    if duplicate_keys:
        for tbl, key, cnt in duplicate_keys:
            lines.append(f"- `{tbl}`: `{key}` x{cnt}")
    else:
        lines.append("- None")

    lines.extend(["", "## Multi-match restore candidates (global_id+geom)", ""])
    if multi_match:
        for tbl, global_id, cnt in multi_match:
            lines.append(f"- `{tbl}` global_id={global_id}: **{cnt}** rows")
    else:
        lines.append("- None")

    lines.extend(["", "## Recent job runs", ""])
    for job_name, status, finished_at, message in job_runs:
        lines.append(f"- **{job_name}** `{status}` @ {finished_at}: {message}")

    lines.append("")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit CRM task sync for data_mos")
    parser.add_argument(
        "--output",
        type=Path,
        help="Write markdown report to this path",
    )
    parser.add_argument(
        "--title",
        default="CRM Task Sync Audit",
    )
    args = parser.parse_args()

    with _conn() as conn:
        conn.autocommit = True
        with conn.cursor() as cur:
            report = render_report(
                title=args.title,
                split_rows=collect_split_rows(cur),
                false_tasked=collect_false_tasked(cur),
                crm_scoped=collect_crm_scoped(cur),
                duplicate_keys=collect_duplicate_task_keys(cur),
                multi_match=collect_multi_match_restore_candidates(cur),
                job_runs=collect_recent_job_runs(cur),
            )

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(report, encoding="utf-8")
        print(f"Wrote {args.output}")
    else:
        print(report)


if __name__ == "__main__":
    main()
