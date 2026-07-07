-- Parent items_* tasked flag: freeze row + split children when CRM-linked.
-- Run before ETL tasked guards and crm_task_sync.

DO $$
DECLARE
    parent_tbl TEXT;
    svc INT;
BEGIN
    FOREACH parent_tbl IN ARRAY ARRAY[
        'items_2855', 'items_62501', 'items_62441', 'items_62461'
    ]
    LOOP
        EXECUTE format(
            'ALTER TABLE data_mos.%I ADD COLUMN IF NOT EXISTS tasked BOOLEAN NOT NULL DEFAULT false',
            parent_tbl
        );
        EXECUTE format(
            'CREATE INDEX IF NOT EXISTS %I ON data_mos.%I (tasked) WHERE tasked',
            parent_tbl || '_tasked_idx',
            parent_tbl
        );
    END LOOP;
END $$;

-- Backfill: parent tasked when any split child has task_key.
UPDATE data_mos.items_2855 p SET tasked = true
WHERE EXISTS (
    SELECT 1 FROM data_mos.items_2855_points c WHERE c.source_id = p.id AND c.task_key IS NOT NULL
    UNION ALL SELECT 1 FROM data_mos.items_2855_lines c WHERE c.source_id = p.id AND c.task_key IS NOT NULL
    UNION ALL SELECT 1 FROM data_mos.items_2855_polygons c WHERE c.source_id = p.id AND c.task_key IS NOT NULL
);

UPDATE data_mos.items_62501 p SET tasked = true
WHERE EXISTS (
    SELECT 1 FROM data_mos.items_62501_points c WHERE c.source_id = p.id AND c.task_key IS NOT NULL
    UNION ALL SELECT 1 FROM data_mos.items_62501_lines c WHERE c.source_id = p.id AND c.task_key IS NOT NULL
    UNION ALL SELECT 1 FROM data_mos.items_62501_polygons c WHERE c.source_id = p.id AND c.task_key IS NOT NULL
);

UPDATE data_mos.items_62441 p SET tasked = true
WHERE EXISTS (
    SELECT 1 FROM data_mos.items_62441_points c WHERE c.source_id = p.id AND c.task_key IS NOT NULL
    UNION ALL SELECT 1 FROM data_mos.items_62441_lines c WHERE c.source_id = p.id AND c.task_key IS NOT NULL
    UNION ALL SELECT 1 FROM data_mos.items_62441_polygons c WHERE c.source_id = p.id AND c.task_key IS NOT NULL
);

UPDATE data_mos.items_62461 p SET tasked = true
WHERE EXISTS (
    SELECT 1 FROM data_mos.items_62461_points c WHERE c.source_id = p.id AND c.task_key IS NOT NULL
    UNION ALL SELECT 1 FROM data_mos.items_62461_lines c WHERE c.source_id = p.id AND c.task_key IS NOT NULL
    UNION ALL SELECT 1 FROM data_mos.items_62461_polygons c WHERE c.source_id = p.id AND c.task_key IS NOT NULL
);
