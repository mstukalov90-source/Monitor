-- One-shot backfill of local-only ozn_date / executor from ozn-tasks/Книга1.xlsx.
-- Match: OrderName first, then "order" for unmatched keys.
-- Not part of nightly ogh_analiz_sync ATTR_COLUMNS.

\set ON_ERROR_STOP on

ALTER TABLE odh_export.ogh_analiz
    ADD COLUMN IF NOT EXISTS ozn_date date,
    ADD COLUMN IF NOT EXISTS executor text;

BEGIN;

CREATE TEMP TABLE ozn_src (
    order_no text PRIMARY KEY,
    ozn_date date NOT NULL,
    executor text NOT NULL
) ON COMMIT DROP;

INSERT INTO ozn_src (order_no, ozn_date, executor) VALUES
    ('12/ОГХ-26/48530', DATE '2026-08-05', 'Слапик И. А.'),
    ('12/ОГХ-26/60947', DATE '2026-08-07', 'Жученко А. А.'),
    ('12/ОГХ-26/68405', DATE '2026-08-12', 'Герасимчук А. М.'),
    ('12/ОГХ-26/49936', DATE '2026-08-12', 'Герасимчук А. М.'),
    ('12/ОГХ-26/49950', DATE '2026-08-12', 'Герасимчук А. М.'),
    ('12/ОГХ-26/49943', DATE '2026-08-12', 'Герасимчук А. М.'),
    ('12/ОГХ-26/66040', DATE '2026-08-12', 'Герасимчук А. М.'),
    ('12/ОГХ-26/66021', DATE '2026-08-12', 'Герасимчук А. М.'),
    ('12/ОГХ-26/50056', DATE '2026-08-12', 'Герасимчук А. М.'),
    ('12/ОГХ-26/50031', DATE '2026-08-12', 'Герасимчук А. М.'),
    ('12/ОГХ-26/66052', DATE '2026-08-12', 'Герасимчук А. М.'),
    ('12/ОГХ-26/49970', DATE '2026-08-12', 'Герасимчук А. М.'),
    ('12/ОГХ-26/49716', DATE '2026-08-12', 'Слапик И. А.'),
    ('12/ОГХ-26/49754', DATE '2026-08-12', 'Слапик И. А.'),
    ('12/ОГХ-26/49436', DATE '2026-08-12', 'Слапик И. А.'),
    ('12/ОГХ-26/49516', DATE '2026-08-12', 'Слапик И. А.'),
    ('12/ОГХ-26/68753', DATE '2026-08-12', 'Слапик И. А.'),
    ('12/ОГХ-26/49678', DATE '2026-08-12', 'Слапик И. А.'),
    ('12/ОГХ-26/49526', DATE '2026-08-12', 'Слапик И. А.'),
    ('12/ОГХ-26/07078', DATE '2026-08-12', 'Синельщиков С. М.'),
    ('12/ОГХ-26/50472', DATE '2026-08-12', 'Слапик И. А.'),
    ('12/ОГХ-26/66302', DATE '2026-07-28', 'Орехов Р. С.'),
    ('12/ОГХ-26/59525', DATE '2026-08-13', 'Жученко А. А.'),
    ('12/ОГХ-26/59524', DATE '2026-08-13', 'Жученко А. А.'),
    ('12/ОГХ-26/59517', DATE '2026-08-13', 'Жученко А. А.'),
    ('12/ОГХ-26/59504', DATE '2026-08-13', 'Жученко А. А.'),
    ('12/ОГХ-26/59508', DATE '2026-08-13', 'Жученко А. А.'),
    ('12/ОГХ-26/65067', DATE '2026-08-11', 'Орехов Р. С.'),
    ('12/ОГХ-26/65074', DATE '2026-08-11', 'Орехов Р. С.'),
    ('12/ОГХ-26/65072', DATE '2026-08-11', 'Орехов Р. С.'),
    ('12/ОГХ-26/65064', DATE '2026-08-11', 'Орехов Р. С.'),
    ('12/ОГХ-26/65073', DATE '2026-08-11', 'Орехов Р. С.'),
    ('12/ОГХ-26/57944', DATE '2026-08-11', 'Скроцкий И. А.'),
    ('12/ОГХ-26/57936', DATE '2026-08-11', 'Скроцкий И. А.'),
    ('12/ОГХ-26/66273', DATE '2026-08-07', 'Жученко А. А.'),
    ('12/ОГХ-26/48518', DATE '2026-08-12', 'Чуйкин М. А.'),
    ('12/ОГХ-26/48655', DATE '2026-08-12', 'Чуйкин М. А.'),
    ('12/ОГХ-26/47172', DATE '2026-08-12', 'Чуйкин М. А.'),
    ('12/ОГХ-26/46593', DATE '2026-08-12', 'Чуйкин М. А.'),
    ('12/ОГХ-26/45988', DATE '2026-08-12', 'Чуйкин М. А.'),
    ('12/ОГХ-26/46158', DATE '2026-07-22', 'Чуйкин М. А.'),
    ('12/ОГХ-26/47094', DATE '2026-08-12', 'Чуйкин М. А.'),
    ('12/ОГХ-26/46923', DATE '2026-08-12', 'Чуйкин М. А.'),
    ('12/ОГХ-26/46891', DATE '2026-08-12', 'Чуйкин М. А.'),
    ('12/ОГХ-26/48282', DATE '2026-08-12', 'Чуйкин М. А.'),
    ('12/ОГХ-26/50137', DATE '2026-08-11', 'Прусов Б. Б.'),
    ('12/ОГХ-26/50140', DATE '2026-08-11', 'Прусов Б. Б.'),
    ('12/ОГХ-26/50142', DATE '2026-08-11', 'Прусов Б. Б.'),
    ('12/ОГХ-26/69469', DATE '2026-08-12', 'Чуйкин М. А.'),
    ('12/ОГХ-26/46812/1', DATE '2026-08-12', 'Герасимчук А. М.'),
    ('12/ОГХ-26/76936', DATE '2026-08-11', 'Орехов Р. С.'),
    ('12/ОГХ-26/76953', DATE '2026-08-12', 'Герасимчук А. М.'),
    ('12/ОГХ-26/49147', DATE '2026-08-12', 'Синельщиков С. М.'),
    ('12/ОГХ-26/77017', DATE '2026-08-12', 'Чуйкин М. А.'),
    ('12/ОГХ-26/51886/1', DATE '2026-08-12', 'Герасимчук А. М.'),
    ('12/ОГХ-26/77420', DATE '2026-08-12', 'Чуйкин М. А.'),
    ('12/ОГХ-26/78783', DATE '2026-08-07', 'Жученко А. А.');

\echo '=== dry-run match report ==='
SELECT
    COUNT(*) AS excel_rows,
    COUNT(*) FILTER (WHERE exists_ordername) AS matched_ordername,
    COUNT(*) FILTER (WHERE exists_order AND NOT exists_ordername) AS matched_order_only,
    COUNT(*) FILTER (WHERE NOT exists_ordername AND NOT exists_order) AS missing
FROM (
    SELECT
        s.order_no,
        EXISTS (
            SELECT 1 FROM odh_export.ogh_analiz t WHERE t."OrderName" = s.order_no
        ) AS exists_ordername,
        EXISTS (
            SELECT 1 FROM odh_export.ogh_analiz t WHERE t."order" = s.order_no
        ) AS exists_order
    FROM ozn_src s
) m;

\echo '=== missing keys (if any) ==='
SELECT s.order_no
FROM ozn_src s
WHERE NOT EXISTS (SELECT 1 FROM odh_export.ogh_analiz t WHERE t."OrderName" = s.order_no)
  AND NOT EXISTS (SELECT 1 FROM odh_export.ogh_analiz t WHERE t."order" = s.order_no)
ORDER BY s.order_no;

WITH matched_ordername AS (
    UPDATE odh_export.ogh_analiz AS t
    SET ozn_date = s.ozn_date,
        executor = s.executor
    FROM ozn_src AS s
    WHERE t."OrderName" = s.order_no
    RETURNING s.order_no
)
UPDATE odh_export.ogh_analiz AS t
SET ozn_date = s.ozn_date,
    executor = s.executor
FROM ozn_src AS s
WHERE t."order" = s.order_no
  AND NOT EXISTS (
      SELECT 1 FROM matched_ordername m WHERE m.order_no = s.order_no
  );

\echo '=== after update ==='
SELECT
    (SELECT COUNT(*) FROM ozn_src) AS excel_rows,
    COUNT(*) FILTER (WHERE t."OrderName" IN (SELECT order_no FROM ozn_src)
                     AND t.ozn_date IS NOT NULL) AS filled_via_ordername,
    COUNT(*) FILTER (WHERE t."order" IN (SELECT order_no FROM ozn_src)
                     AND t."OrderName" NOT IN (SELECT order_no FROM ozn_src)
                     AND t.ozn_date IS NOT NULL) AS filled_via_order,
    (SELECT COUNT(*) FROM odh_export.ogh_analiz WHERE ozn_date IS NOT NULL) AS with_date,
    (SELECT COUNT(*) FROM odh_export.ogh_analiz WHERE executor IS NOT NULL) AS with_exec
FROM odh_export.ogh_analiz t;

COMMIT;
