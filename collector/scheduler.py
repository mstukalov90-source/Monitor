"""
Scheduler for MONITOR data collector.

Daily schedule (Europe/Moscow):
  01:00 — data_mos_2855 export + load
  01:30 — data_mos_2941 export + load
  02:00 — data_mos_62461 export + load
  02:30 — data_mos_62501 export + load
  04:00 — lens sync from remote SPS
  05:00 — genplan response_*.json import
"""

from __future__ import annotations

import argparse
import logging
import sys

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from collector.config import DATA_MOS_EXPORTS, TZ
from collector.jobs import data_mos_job, genplan_job, lens_sync_job

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("collector.scheduler")

JOBS = {
    "data_mos": data_mos_job.run_all_data_mos,
    "data_mos_2855": data_mos_job.run_2855,
    "data_mos_2941": data_mos_job.run_2941,
    "data_mos_62461": data_mos_job.run_62461,
    "data_mos_62501": data_mos_job.run_62501,
    "lens_sync": lens_sync_job.run,
    "genplan": genplan_job.run,
}

_DATA_MOS_CRON = {
    2855: (1, 0),
    2941: (1, 30),
    62461: (2, 0),
    62501: (2, 30),
}


def run_job(name: str) -> None:
    if name not in JOBS:
        raise ValueError(f"Unknown job: {name}. Available: {list(JOBS)}")
    logger.info("Running job: %s", name)
    JOBS[name]()


def start_scheduler() -> None:
    scheduler = BlockingScheduler(timezone=TZ)

    for config in DATA_MOS_EXPORTS:
        hour, minute = _DATA_MOS_CRON[config.service_id]
        scheduler.add_job(
            data_mos_job.run_for,
            CronTrigger(hour=hour, minute=minute, timezone=TZ),
            args=[config],
            id=config.job_name,
            name=f"Data MOS export {config.service_id}",
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
    for config in DATA_MOS_EXPORTS:
        hour, minute = _DATA_MOS_CRON[config.service_id]
        logger.info("  %02d:%02d — %s", hour, minute, config.job_name)
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
