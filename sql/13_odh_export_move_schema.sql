-- Move ogh-disruption from hyphenated schema "odh-export" to odh_export.

CREATE SCHEMA IF NOT EXISTS odh_export;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM information_schema.tables
        WHERE table_schema = 'odh-export'
          AND table_name = 'ogh-disruption'
    ) AND NOT EXISTS (
        SELECT 1
        FROM information_schema.tables
        WHERE table_schema = 'odh_export'
          AND table_name = 'ogh-disruption'
    ) THEN
        ALTER TABLE "odh-export"."ogh-disruption" SET SCHEMA odh_export;
    ELSIF EXISTS (
        SELECT 1
        FROM information_schema.tables
        WHERE table_schema = 'odh-export'
          AND table_name = 'ogh-disruption'
    ) AND EXISTS (
        SELECT 1
        FROM information_schema.tables
        WHERE table_schema = 'odh_export'
          AND table_name = 'ogh-disruption'
    ) THEN
        IF (SELECT COUNT(*) FROM odh_export."ogh-disruption") = 0
           AND (SELECT COUNT(*) FROM "odh-export"."ogh-disruption") > 0 THEN
            DROP TABLE odh_export."ogh-disruption";
            ALTER TABLE "odh-export"."ogh-disruption" SET SCHEMA odh_export;
        END IF;
    END IF;
END $$;
