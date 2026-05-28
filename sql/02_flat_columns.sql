-- Migrate existing payload-based tables to flattened column layout.
-- Safe to run on fresh DB (no-op if tables already migrated).

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'data_mos' AND table_name = 'items' AND column_name = 'payload'
    ) THEN
        CREATE TABLE data_mos.items_new (
            id                          BIGSERIAL PRIMARY KEY,
            dataset_id                  INTEGER,
            row_id                      TEXT,
            version_number              TEXT,
            release_number              TEXT,
            order_number                TEXT,
            order_date                  TEXT,
            customer_construction       TEXT,
            customer_construction_inn   TEXT,
            general_contractor          TEXT,
            general_contractor_inn      TEXT,
            work_type                   JSONB,
            order_work                  JSONB,
            earthwork_objectives        JSONB,
            objectives_temp_fences      JSONB,
            objectives_temp_objects     JSONB,
            address_nearby_building     TEXT,
            adm_area                    TEXT,
            district                    TEXT,
            work_place_description      TEXT,
            work_start_date             TEXT,
            work_end_date               TEXT,
            global_id                   BIGINT,
            geom                        GEOMETRY(Geometry, 4326),
            loaded_at                   TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );

        INSERT INTO data_mos.items_new (
            dataset_id, row_id, version_number, release_number,
            order_number, order_date, customer_construction, customer_construction_inn,
            general_contractor, general_contractor_inn,
            work_type, order_work, earthwork_objectives,
            objectives_temp_fences, objectives_temp_objects,
            address_nearby_building, adm_area, district, work_place_description,
            work_start_date, work_end_date, global_id, geom, loaded_at
        )
        SELECT
            NULLIF(payload->>'datasetId', '')::INTEGER,
            NULLIF(payload->>'rowId', ''),
            NULLIF(payload->>'versionNumber', ''),
            NULLIF(payload->>'releaseNumber', ''),
            payload->'attributes'->>'OrderNumber',
            payload->'attributes'->>'OrderDate',
            payload->'attributes'->>'CustomerConstruction',
            payload->'attributes'->>'CustomerConstructionINN',
            payload->'attributes'->>'GeneralContractor',
            payload->'attributes'->>'GeneralContractorINN',
            CASE WHEN jsonb_typeof(payload->'attributes'->'WorkType') IN ('array','object')
                 THEN payload->'attributes'->'WorkType' END,
            CASE WHEN jsonb_typeof(payload->'attributes'->'OrderWork') IN ('array','object')
                 THEN payload->'attributes'->'OrderWork' END,
            CASE WHEN jsonb_typeof(payload->'attributes'->'EarthworkObjectives') IN ('array','object')
                 THEN payload->'attributes'->'EarthworkObjectives' END,
            CASE WHEN jsonb_typeof(payload->'attributes'->'ObjectivesOfTheInstallationOfTemporaryFences') IN ('array','object')
                 THEN payload->'attributes'->'ObjectivesOfTheInstallationOfTemporaryFences' END,
            CASE WHEN jsonb_typeof(payload->'attributes'->'ObjectivesOfThePlacementOfTemporaryObjects') IN ('array','object')
                 THEN payload->'attributes'->'ObjectivesOfThePlacementOfTemporaryObjects' END,
            payload->'attributes'->>'AddressOfNearbyBuilding',
            payload->'attributes'->>'AdmArea',
            payload->'attributes'->>'District',
            payload->'attributes'->>'WorkPlaceDescription',
            payload->'attributes'->>'WorkStartDate',
            payload->'attributes'->>'WorkEndDate',
            NULLIF(payload->'attributes'->>'global_id', '')::BIGINT,
            geom,
            loaded_at
        FROM data_mos.items;

        DROP TABLE data_mos.items;
        ALTER TABLE data_mos.items_new RENAME TO items;

        CREATE INDEX IF NOT EXISTS idx_data_mos_items_geom ON data_mos.items USING GIST (geom);
        CREATE INDEX IF NOT EXISTS idx_data_mos_items_order_number ON data_mos.items (order_number);
        CREATE INDEX IF NOT EXISTS idx_data_mos_items_loaded_at ON data_mos.items (loaded_at DESC);
    END IF;

    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'genplan' AND table_name = 'responses' AND column_name = 'payload'
    ) THEN
        CREATE TABLE genplan.responses_new (
            id                  BIGSERIAL PRIMARY KEY,
            file_name           TEXT NOT NULL,
            opening             BOOLEAN,
            legal               BOOLEAN,
            description         TEXT,
            image               TEXT,
            photo_lat           DOUBLE PRECISION,
            photo_lng           DOUBLE PRECISION,
            photo_azimuth_deg   INTEGER,
            order_source        TEXT,
            order_doc_num       TEXT,
            order_work_types    TEXT,
            order_date_start    DATE,
            order_date_end      DATE,
            order_customer      TEXT,
            order_status        TEXT,
            yolo_label          INTEGER,
            yolo_votes          JSONB,
            geom                GEOMETRY(Geometry, 4326),
            photo_geom          GEOMETRY(Point, 4326),
            loaded_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );

        INSERT INTO genplan.responses_new (
            file_name, opening, legal, description, image,
            photo_lat, photo_lng, photo_azimuth_deg,
            order_source, order_doc_num, order_work_types,
            order_date_start, order_date_end, order_customer, order_status,
            yolo_label, yolo_votes, geom, photo_geom, loaded_at
        )
        SELECT
            file_name,
            (payload->>'opening')::BOOLEAN,
            (payload->>'legal')::BOOLEAN,
            payload->>'description',
            payload->>'image',
            (payload->'photo_coordinate'->>'lat')::DOUBLE PRECISION,
            (payload->'photo_coordinate'->>'lng')::DOUBLE PRECISION,
            (payload->'photo_coordinate'->>'azimuth_deg')::INTEGER,
            payload->'order'->>'source',
            payload->'order'->>'doc_num',
            payload->'order'->>'work_types',
            NULLIF(payload->'order'->>'date_start', '')::DATE,
            NULLIF(payload->'order'->>'date_end', '')::DATE,
            payload->'order'->>'customer',
            payload->'order'->>'status',
            (payload->'yolo'->>'label')::INTEGER,
            payload->'yolo'->'votes',
            geom,
            CASE
                WHEN payload->'photo_coordinate' ? 'lat' AND payload->'photo_coordinate' ? 'lng'
                THEN ST_SetSRID(ST_MakePoint(
                    (payload->'photo_coordinate'->>'lng')::FLOAT,
                    (payload->'photo_coordinate'->>'lat')::FLOAT
                ), 4326)
            END,
            loaded_at
        FROM genplan.responses;

        DROP TABLE genplan.responses;
        ALTER TABLE genplan.responses_new RENAME TO responses;

        CREATE INDEX IF NOT EXISTS idx_genplan_responses_geom ON genplan.responses USING GIST (geom);
        CREATE INDEX IF NOT EXISTS idx_genplan_responses_photo_geom ON genplan.responses USING GIST (photo_geom);
        CREATE INDEX IF NOT EXISTS idx_genplan_responses_file_name ON genplan.responses (file_name);
        CREATE INDEX IF NOT EXISTS idx_genplan_responses_loaded_at ON genplan.responses (loaded_at DESC);
    END IF;
END $$;
