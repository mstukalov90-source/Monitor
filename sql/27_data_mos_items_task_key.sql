-- task_key on data_mos split tables: stable link to crm.tasks(key).
-- Deploy before WebCRM sql/23-25 and ETL merge-load changes.

DO $$
DECLARE
    tbl TEXT;
BEGIN
    FOREACH tbl IN ARRAY ARRAY[
        'items_2855_points', 'items_2855_lines', 'items_2855_polygons',
        'items_62501_points', 'items_62501_lines', 'items_62501_polygons',
        'items_62441_points', 'items_62441_lines', 'items_62441_polygons',
        'items_62461_points', 'items_62461_lines', 'items_62461_polygons'
    ]
    LOOP
        EXECUTE format(
            'ALTER TABLE data_mos.%I ADD COLUMN IF NOT EXISTS task_key UUID REFERENCES crm.tasks(key) ON DELETE SET NULL',
            tbl
        );
        EXECUTE format(
            'CREATE UNIQUE INDEX IF NOT EXISTS %I ON data_mos.%I (task_key) WHERE task_key IS NOT NULL',
            tbl || '_uq_task_key',
            tbl
        );
    END LOOP;
END $$;
