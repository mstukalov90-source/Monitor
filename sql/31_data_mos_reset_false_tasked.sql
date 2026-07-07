-- Reset parent items_* tasked flag from actual split-child task_key links.
-- Idempotent: same logic as refresh_all_tasked_parents() in collector.

DO $$
DECLARE
    parent_tbl TEXT;
BEGIN
    FOREACH parent_tbl IN ARRAY ARRAY[
        'items_2855', 'items_62501', 'items_62441', 'items_62461'
    ]
    LOOP
        EXECUTE format($sql$
            UPDATE data_mos.%I p
            SET tasked = (
                EXISTS (
                    SELECT 1 FROM data_mos.%I_points c
                    WHERE c.source_id = p.id AND c.task_key IS NOT NULL
                )
                OR EXISTS (
                    SELECT 1 FROM data_mos.%I_lines c
                    WHERE c.source_id = p.id AND c.task_key IS NOT NULL
                )
                OR EXISTS (
                    SELECT 1 FROM data_mos.%I_polygons c
                    WHERE c.source_id = p.id AND c.task_key IS NOT NULL
                )
            )
        $sql$, parent_tbl, parent_tbl, parent_tbl, parent_tbl);
    END LOOP;
END $$;
