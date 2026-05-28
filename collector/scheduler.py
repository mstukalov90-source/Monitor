"""
Scheduler for MONITOR data collector.

Daily schedule (Europe/Moscow):
  03:00 — data_mos export + load
  04:00 — lens sync from remote SPS
  05:00 — genplan response_*.json import
"""

from __future__ import annotations

import argparse
import logging
import sys

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from collector.config import TZ
from collector.jobs import data_mos_job, genplan_job, lens_sync_job

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("collector.scheduler")

JOBS = {
    "data_mos": data_mos_job.run,
    "lens_sync": lens_sync_job.run,
    "genplan": genplan_job.run,
}


def run_job(name: str) -> None:
    if name not in JOBS:
        raise ValueError(f"Unknown job: {name}. Available: {list(JOBS)}")
    logger.info("Running job: %s", name)
    JOBS[name]()


def start_scheduler() -> None:
    scheduler = BlockingScheduler(timezone=TZ)

    scheduler.add_job(
        data_mos_job.run,
        CronTrigger(hour=3, minute=0, timezone=TZ),
        id="data_mos",
        name="Data MOS export and load",
        replace_existing=True,
    )
    scheduler.add_job(
        lens_sync_job.run,
        CronTrigger(hour=4, minute=0, timezone=TZ),
        id="lens_sync",
        name="Lens sync from remote SPS",
        replace_existing=True,
    )
    scheduler.add_job(
        genplan_job.run,
        CronTrigger(hour=5, minute=0, timezone=TZ),
        id="genplan",
        name="Genplan response JSON import",
        replace_existing=True,
    )

    logger.info("Scheduler started (timezone=%s)", TZ)
    logger.info("  03:00 — data_mos")
    logger.info("  04:00 — lens_sync")
    logger.info("  05:00 — genplan")

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
        for name in JOBS:
            run_job(name)
    else:
        start_scheduler()


if __name__ == "__main__":
    main()
