-- PostGIS helper: convert nearly-closed lines to polygons (ad-hoc queries).
-- Primary ETL path uses collector/geom_line_to_polygon.py after data_mos load.

CREATE SCHEMA IF NOT EXISTS data_mos;

CREATE OR REPLACE FUNCTION data_mos._multiline_to_ring(geom geometry)
RETURNS geometry
LANGUAGE sql
IMMUTABLE
AS $$
    SELECT ST_MakeLine(ST_Collect(pts ORDER BY line_idx, pt_idx))
    FROM (
        SELECT
            (d).path[1] AS line_idx,
            (dp).path[1] AS pt_idx,
            (dp).geom AS pts
        FROM ST_Dump(geom) AS d,
             LATERAL ST_DumpPoints((d).geom) AS dp
    ) ordered;
$$;

CREATE OR REPLACE FUNCTION data_mos.try_line_to_polygon(
    geom geometry,
    threshold double precision DEFAULT 0.1
)
RETURNS geometry
LANGUAGE plpgsql
IMMUTABLE
AS $$
DECLARE
    gtype text;
    total_len double precision;
    gap double precision;
    ring geometry;
    result geometry;
    first_line geometry;
    last_line geometry;
BEGIN
    IF geom IS NULL OR ST_IsEmpty(geom) THEN
        RETURN NULL;
    END IF;

    gtype := ST_GeometryType(geom);

    IF gtype = 'ST_LineString' THEN
        IF ST_NPoints(geom) < 3 THEN
            RETURN NULL;
        END IF;

        total_len := ST_Length(geom::geography);
        IF total_len <= 0 THEN
            RETURN NULL;
        END IF;

        gap := ST_Distance(
            ST_StartPoint(geom)::geography,
            ST_EndPoint(geom)::geography
        );

        IF NOT ST_IsClosed(geom) AND gap / total_len >= threshold THEN
            RETURN NULL;
        END IF;

        IF ST_IsClosed(geom) THEN
            ring := geom;
        ELSE
            ring := ST_AddPoint(geom, ST_StartPoint(geom));
        END IF;

    ELSIF gtype = 'ST_MultiLineString' THEN
        SELECT
            (SELECT (d).geom FROM ST_Dump(geom) AS d ORDER BY (d).path LIMIT 1),
            (SELECT (d).geom FROM ST_Dump(geom) AS d ORDER BY (d).path DESC LIMIT 1),
            (SELECT COALESCE(sum(ST_Length((d).geom::geography)), 0) FROM ST_Dump(geom) AS d)
        INTO first_line, last_line, total_len;

        IF total_len <= 0 OR first_line IS NULL OR last_line IS NULL THEN
            RETURN NULL;
        END IF;

        gap := ST_Distance(
            ST_StartPoint(first_line)::geography,
            ST_EndPoint(last_line)::geography
        );

        IF gap / total_len >= threshold THEN
            RETURN NULL;
        END IF;

        ring := ST_LineMerge(geom);
        IF ST_GeometryType(ring) <> 'ST_LineString' THEN
            ring := data_mos._multiline_to_ring(geom);
        END IF;

        IF ring IS NULL OR ST_NPoints(ring) < 3 THEN
            RETURN NULL;
        END IF;

        IF NOT ST_IsClosed(ring) THEN
            ring := ST_AddPoint(ring, ST_StartPoint(ring));
        END IF;
    ELSE
        RETURN NULL;
    END IF;

    BEGIN
        result := ST_MakePolygon(ring);
        result := ST_MakeValid(result);

        IF ST_GeometryType(result) = 'ST_MultiPolygon' THEN
            SELECT (d).geom
            INTO result
            FROM ST_Dump(result) AS d
            ORDER BY ST_Area((d).geom::geography) DESC
            LIMIT 1;
        END IF;

        IF result IS NULL
           OR ST_GeometryType(result) <> 'ST_Polygon'
           OR ST_Area(result::geography) < 1 THEN
            RETURN NULL;
        END IF;

        RETURN ST_SetSRID(result, ST_SRID(geom));
    EXCEPTION
        WHEN OTHERS THEN
            RETURN NULL;
    END;
END;
$$;
