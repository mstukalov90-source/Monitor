-- Link field reports to CRM task area (crm.tasks_area.key).

ALTER TABLE mggt_field.reports
    ADD COLUMN IF NOT EXISTS tasks_key UUID NULL;

CREATE INDEX IF NOT EXISTS idx_mggt_field_reports_tasks_key
    ON mggt_field.reports (tasks_key);
