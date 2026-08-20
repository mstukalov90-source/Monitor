"""
Scheduler for MONITOR data collector.

Daily schedule (Europe/Moscow):
  00:01 — genplan_uuid_api_pipeline: uuid_api meta → crm.tasks → download
  02:00 — ogh_analiz_sync: read-only gis.ogh_analiz (mggt_asu) → odh_export.ogh_analiz
  03:00 — data_mos (all 8 exports sequentially), then ogh_disruption if mggt_dgn.geojson exists
  03:30 — crm_task_sync_audit
  04:00 — lens_pipeline: lens_sync, then stroymonitoring_sync
  06:00 — vector_stroy_url_222: fetch map221/rs_2022 + DROP + GeoJSON upsert
  22:00 — ogh_disruption_topotext: matching topopassport.topotext → odh_export.ogh-disruption
  22:15 — ogh_disruption_topo_texts: matching t500.topo_texts (mggt) → odh_export.ogh-disruption
  22:25 — ogh_disruption_crm_tasks: new odh_export.ogh-disruption rows → crm.tasks

Monthly (Europe/Moscow):
  01:00 first Saturday — data_mos_60562 (export + TRUNCATE load, no purge/split)

  genplan_pipeline (genplan_fetch + import) — manual only: --run genplan_pipeline
  genplan_upload — manual only: --run genplan_upload
  genplan_upload_pipeline — genplan_upload → genplan_fetch_uploaded → genplan (manual)
  genplan_fetch_uuid_api — meta for genplan.uuid_api UUIDs (manual)
  genplan_download — download photos (disruption=true) to downloaded_photo/ (manual)
  backfill_ai_photo_tasks — one-time crm.tasks from genplan.photo_meta (manual)
  backfill_data_mos_crm_tasks — backfill crm.tasks for data_mos split tables (manual)
  ogh_analiz_sync_orders — one-time ogh_analiz rows by "OrderName" list (manual)
  ozn_excel_inbox — every 15s: Excel from excel_inbox → ogh_analiz.ozn_date/executor
  23:00 — situation_photo_upload: situation share photos → MSI Holes (read-only share)
  situation_photo_upload_dry — same SELECT/path inspect, no API
  23:30 — ogh_order_photo_upload: OGH Заказы field photos → MSI Holes (read-only share)
  ogh_order_photo_upload_dry — same SELECT/path inspect, no API
"""

from __future__ import annotations

import argparse
import logging
import sys
from typing import Callable

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from collector.config import DATA_MOS_EXPORTS, DATA_MOS_MONTHLY_EXPORTS, TZ
from collector.jobs import (
    backfill_ai_photo_tasks_job,
    backfill_data_mos_crm_tasks_job,
    crm_task_sync_audit_job,
    data_mos_job,
    genplan_download_job,
    genplan_fetch_job,
    genplan_fetch_uploaded_job,
    genplan_fetch_uuid_api_job,
    genplan_job,
    genplan_upload_job,
    lens_sync_job,
    ogh_analiz_sync_job,
    ogh_disruption_crm_tasks_job,
    ogh_disruption_job,
    ogh_disruption_topo_texts_job,
    ogh_disruption_topotext_job,
    ogh_order_photo_upload_job,
    ozn_excel_inbox_job,
    situation_photo_upload_job,
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
    """Upload local photos, fetch their meta from MSI Holes, import any JSON."""
    genplan_upload_job.run()
    genplan_fetch_uploaded_job.run()
    genplan_job.run()


def run_genplan_uuid_api_pipeline() -> None:
    """Fetch uuid_api meta, create crm.tasks for disruption, download photos."""
    genplan_fetch_uuid_api_job.run()
    backfill_ai_photo_tasks_job.run()
    genplan_download_job.run()


def _build_jobs() -> dict[str, Callable[[], None]]:
    jobs: dict[str, Callable[[], None]] = {
        "data_mos": data_mos_job.run_all_data_mos,
        "ogh_analiz_sync": ogh_analiz_sync_job.run,
        "ogh_analiz_sync_orders": ogh_analiz_sync_job.run_orders_once,
        "ogh_disruption": ogh_disruption_job.run,
        "ogh_disruption_topotext": ogh_disruption_topotext_job.run,
        "ogh_disruption_topo_texts": ogh_disruption_topo_texts_job.run,
        "ogh_disruption_crm_tasks": ogh_disruption_crm_tasks_job.run,
        "lens_pipeline": run_lens_pipeline,
        "lens_sync": lens_sync_job.run,
        "stroymonitoring_sync": stroymonitoring_sync_job.run,
        "genplan_fetch": genplan_fetch_job.run,
        "genplan_fetch_uploaded": genplan_fetch_uploaded_job.run,
        "genplan_fetch_uuid_api": genplan_fetch_uuid_api_job.run,
        "genplan": genplan_job.run,
        "genplan_upload": genplan_upload_job.run,
        "genplan_download": genplan_download_job.run,
        "backfill_ai_photo_tasks": backfill_ai_photo_tasks_job.run,
        "backfill_data_mos_crm_tasks": backfill_data_mos_crm_tasks_job.run,
        "crm_task_sync_audit": crm_task_sync_audit_job.run,
        "genplan_pipeline": run_genplan_pipeline,
        "genplan_upload_pipeline": run_genplan_upload_pipeline,
        "genplan_uuid_api_pipeline": run_genplan_uuid_api_pipeline,
        "vector_stroy_url_222": vector_stroy_job.run,
        "ozn_excel_inbox": ozn_excel_inbox_job.run,
        "ogh_order_photo_upload": ogh_order_photo_upload_job.run,
        "ogh_order_photo_upload_dry": ogh_order_photo_upload_job.run_dry,
        "situation_photo_upload": situation_photo_upload_job.run,
        "situation_photo_upload_dry": situation_photo_upload_job.run_dry,
    }
    for config in DATA_MOS_EXPORTS:
        jobs[config.job_name] = lambda c=config: data_mos_job.run_for(c)
    for config in DATA_MOS_MONTHLY_EXPORTS:
        jobs[config.job_name] = lambda c=config: data_mos_job.run_for(c)
    return jobs


JOBS = _build_jobs()

# Order for --run-all (no duplicate lens / stroymonitoring entries).
RUN_ALL_ORDER: tuple[str, ...] = (
    "ogh_analiz_sync",
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


def _run_monthly_data_mos() -> None:
    for config in DATA_MOS_MONTHLY_EXPORTS:
        data_mos_job.run_for(config)


def start_scheduler() -> None:
    scheduler = BlockingScheduler(timezone=TZ)

    scheduler.add_job(
        run_genplan_uuid_api_pipeline,
        CronTrigger(hour=0, minute=1, timezone=TZ),
        id="genplan_uuid_api_pipeline",
        name="uuid_api meta → crm.tasks → download",
        replace_existing=True,
    )
    scheduler.add_job(
        _run_monthly_data_mos,
        CronTrigger(day="1-7", day_of_week="sat", hour=1, minute=0, timezone=TZ),
        id="data_mos_monthly",
        name="Data MOS monthly exports (first Saturday)",
        replace_existing=True,
    )
    scheduler.add_job(
        ogh_analiz_sync_job.run,
        CronTrigger(hour=2, minute=0, timezone=TZ),
        id="ogh_analiz_sync",
        name="Read-only ogh_analiz sync (mggt_asu → odh_export)",
        replace_existing=True,
    )
    scheduler.add_job(
        data_mos_job.run_all_data_mos,
        CronTrigger(hour=3, minute=0, timezone=TZ),
        id="data_mos",
        name="Data MOS export (all services)",
        replace_existing=True,
    )
    scheduler.add_job(
        crm_task_sync_audit_job.run,
        CronTrigger(hour=3, minute=30, timezone=TZ),
        id="crm_task_sync_audit",
        name="CRM task sync audit",
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
        name="Vector stroy url_222 fetch + DROP + GeoJSON upsert",
        replace_existing=True,
    )
    scheduler.add_job(
        ogh_disruption_topotext_job.run,
        CronTrigger(hour=22, minute=0, timezone=TZ),
        id="ogh_disruption_topotext",
        name="Read-only topotext labels (mggt_asu → odh_export.ogh-disruption)",
        replace_existing=True,
    )
    scheduler.add_job(
        ogh_disruption_topo_texts_job.run,
        CronTrigger(hour=22, minute=15, timezone=TZ),
        id="ogh_disruption_topo_texts",
        name="Read-only t500.topo_texts labels (mggt → odh_export.ogh-disruption)",
        replace_existing=True,
    )
    scheduler.add_job(
        ogh_disruption_crm_tasks_job.run,
        CronTrigger(hour=22, minute=25, timezone=TZ),
        id="ogh_disruption_crm_tasks",
        name="New odh_export.ogh-disruption rows → crm.tasks",
        replace_existing=True,
    )

    scheduler.add_job(
        ozn_excel_inbox_job.run,
        IntervalTrigger(seconds=15, timezone=TZ),
        id="ozn_excel_inbox",
        name="Excel inbox → ogh_analiz ozn_date/executor",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        situation_photo_upload_job.run,
        CronTrigger(hour=23, minute=0, timezone=TZ),
        id="situation_photo_upload",
        name="situation share photos → MSI Holes",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        ogh_order_photo_upload_job.run,
        CronTrigger(hour=23, minute=30, timezone=TZ),
        id="ogh_order_photo_upload",
        name="OGH Заказы field photos → MSI Holes",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )

    logger.info("Scheduler started (timezone=%s)", TZ)
    logger.info("  00:01 — genplan_uuid_api_pipeline")
    logger.info(
        "  01:00 first Saturday — data_mos monthly (%s)",
        ", ".join(c.job_name for c in DATA_MOS_MONTHLY_EXPORTS),
    )
    logger.info("  02:00 — ogh_analiz_sync (mggt_asu gis.ogh_analiz, read-only)")
    logger.info("  03:00 — data_mos (%s services), then ogh_disruption", len(DATA_MOS_EXPORTS))
    for config in DATA_MOS_EXPORTS:
        logger.info("         — %s", config.job_name)
    logger.info("         — ogh_disruption (mggt_dgn/mggt_dgn.geojson, if present)")
    logger.info("  03:30 — crm_task_sync_audit")
    logger.info("  04:00 — lens_pipeline (lens_sync → stroymonitoring_sync)")
    logger.info("  06:00 — vector_stroy_url_222")
    logger.info("  22:00 — ogh_disruption_topotext (mggt_asu topopassport.topotext)")
    logger.info("  22:15 — ogh_disruption_topo_texts (mggt t500.topo_texts)")
    logger.info("  22:25 — ogh_disruption_crm_tasks (ogh-disruption → crm.tasks)")
    logger.info("  23:00 — situation_photo_upload (situation fnm → genplan API)")
    logger.info("  23:30 — ogh_order_photo_upload (Заказы/02_Поле/Фото → genplan API)")
    logger.info("  every 15s — ozn_excel_inbox (excel_inbox → ozn_date/executor)")
    logger.info("  (genplan_pipeline — manual only: --run genplan_pipeline)")
    logger.info("  (genplan_upload — manual only: --run genplan_upload)")
    logger.info("  (genplan_fetch_uploaded — manual only: --run genplan_fetch_uploaded)")
    logger.info("  (genplan_fetch_uuid_api — manual only: --run genplan_fetch_uuid_api)")
    logger.info("  (genplan_download — manual only: --run genplan_download)")
    logger.info("  (backfill_ai_photo_tasks — manual only: --run backfill_ai_photo_tasks)")
    logger.info("  (backfill_data_mos_crm_tasks — manual only: --run backfill_data_mos_crm_tasks)")
    logger.info("  (ogh_analiz_sync_orders — manual only: --run ogh_analiz_sync_orders)")
    logger.info("  (ogh_order_photo_upload_dry — manual only: --run ogh_order_photo_upload_dry)")
    logger.info("  (situation_photo_upload_dry — manual only: --run situation_photo_upload_dry)")
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
