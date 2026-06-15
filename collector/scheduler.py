"""
Scheduler for MONITOR data collector.

Daily schedule (Europe/Moscow):
  03:00 — data_mos (all 8 exports sequentially), then ogh_disruption if mggt_dgn.geojson exists
  04:00 — lens_pipeline: lens_sync, then stroymonitoring_sync
  06:00 — vector_stroy_url_222 GeoJSON upsert

  genplan_pipeline (genplan_fetch + import) — manual only: --run genplan_pipeline
  genplan_upload — manual only: --run genplan_upload
  genplan_upload_pipeline — genplan_upload → genplan_fetch → genplan (manual)
"""

from __future__ import annotations

import argparse
import logging
import sys
from typing import Callable

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from collector.config import DATA_MOS_EXPORTS, TZ
from collector.jobs import (
    data_mos_job,
    genplan_fetch_job,
    genplan_job,
    genplan_upload_job,
    lens_sync_job,
    ogh_disruption_job,
    stroymonitoring_sync_job,
    vector_stroy_job,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("collector.scheduler")


def run_lens_pipeline() -> None:
    """Run lens_sync then stroymonitoring_sync (04:00 chain)."""
    lens_sync_job.run()
    stroymonitoring_sync_job.run()


def run_genplan_pipeline() -> None:
    """Run genplan_fetch then genplan import (05:00 chain)."""
    genplan_fetch_job.run()
    genplan_job.run()


def run_genplan_upload_pipeline() -> None:
    """Upload local photos, then fetch meta and import JSON."""
    genplan_upload_job.run()
    genplan_fetch_job.run()
    genplan_job.run()


def _build_jobs() -> dict[str, Callable[[], None]]:
    jobs: dict[str, Callable[[], None]] = {
        "data_mos": data_mos_job.run_all_data_mos,
        "ogh_disruption": ogh_disruption_job.run,
        "lens_pipeline": run_lens_pipeline,
        "lens_sync": lens_sync_job.run,
        "stroymonitoring_sync": stroymonitoring_sync_job.run,
        "genplan_fetch": genplan_fetch_job.run,
        "genplan": genplan_job.run,
        "genplan_upload": genplan_upload_job.run,
        "genplan_pipeline": run_genplan_pipeline,
        "genplan_upload_pipeline": run_genplan_upload_pipeline,
        "vector_stroy_url_222": vector_stroy_job.run,
    }
    for config in DATA_MOS_EXPORTS:
        jobs[config.job_name] = lambda c=config: data_mos_job.run_for(c)
    return jobs


JOBS = _build_jobs()

# Order for --run-all (no duplicate lens / stroymonitoring entries).
RUN_ALL_ORDER: tuple[str, ...] = (
    "data_mos",
    "ogh_disruption",
    "lens_pipeline",
    "vector_stroy_url_222",
)


def run_job(name: str) -> None:
    if name not in JOBS:
        raise ValueError(f"Unknown job: {name}. Available: {list(JOBS)}")
    logger.info("Running job: %s", name)
    JOBS[name]()


def start_scheduler() -> None:
    scheduler = BlockingScheduler(timezone=TZ)

    scheduler.add_job(
        data_mos_job.run_all_data_mos,
        CronTrigger(hour=3, minute=0, timezone=TZ),
        id="data_mos",
        name="Data MOS export (all services)",
        replace_existing=True,
    )
    scheduler.add_job(
        run_lens_pipeline,
        CronTrigger(hour=4, minute=0, timezone=TZ),
        id="lens_pipeline",
        name="Lens sync + stroymonitoring sync",
        replace_existing=True,
    )
    scheduler.add_job(
        vector_stroy_job.run,
        CronTrigger(hour=6, minute=0, timezone=TZ),
        id="vector_stroy_url_222",
        name="Vector stroy url_222 GeoJSON upsert",
        replace_existing=True,
    )

    logger.info("Scheduler started (timezone=%s)", TZ)
    logger.info("  03:00 — data_mos (%s services), then ogh_disruption", len(DATA_MOS_EXPORTS))
    for config in DATA_MOS_EXPORTS:
        logger.info("         — %s", config.job_name)
    logger.info("         — ogh_disruption (mggt_dgn/mggt_dgn.geojson, if present)")
    logger.info("  04:00 — lens_pipeline (lens_sync → stroymonitoring_sync)")
    logger.info("  06:00 — vector_stroy_url_222")
    logger.info("  (genplan_pipeline — manual only: --run genplan_pipeline)")
    logger.info("  (genplan_upload — manual only: --run genplan_upload)")

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Scheduler stopped")


def main() -> None:
    parser = argparse.ArgumentParser(description="MONITOR data collector scheduler")
    parser.add_argument(
        "--run",
        choices=list(JOBS.keys()),
        help="Run a single job immediately and exit",
    )
    parser.add_argument(
        "--run-all",
        action="store_true",
        help="Run all jobs sequentially and exit",
    )
    args = parser.parse_args()

    if args.run:
        run_job(args.run)
    elif args.run_all:
        for name in RUN_ALL_ORDER:
            run_job(name)
    else:
        start_scheduler()


if __name__ == "__main__":
    main()
