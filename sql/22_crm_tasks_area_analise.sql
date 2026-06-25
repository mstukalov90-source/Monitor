-- CRM task area: analysis flag (default false for all rows).

ALTER TABLE crm.tasks_area
    ADD COLUMN IF NOT EXISTS analise BOOLEAN NOT NULL DEFAULT false;

UPDATE crm.tasks_area
SET analise = false
WHERE analise IS DISTINCT FROM false;
