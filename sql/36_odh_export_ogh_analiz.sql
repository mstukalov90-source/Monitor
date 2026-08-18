-- Mirror of mggt_asu.gis.ogh_analiz in odh_export, stored as WGS84 (EPSG:4326).
-- Source geometry is MSK-77 (SRID 980077); transform happens in the collector job.

CREATE EXTENSION IF NOT EXISTS postgis;

CREATE SCHEMA IF NOT EXISTS odh_export;

-- Moscow MGGT (MSK-77) — same definition as sql/20_mggt_station_tables.sql.
INSERT INTO spatial_ref_sys (srid, auth_name, auth_srid, proj4text, srtext)
VALUES (
    980077,
    'MSK_77',
    980077,
    '+proj=tmerc +lat_0=55.66666666667 +lon_0=37.5 +k=1 +x_0=0 +y_0=0 +ellps=bessel +towgs84=458.475,0.244,603.087,-3.98169,-0.43293,4.43381,1.713 +units=m +no_defs',
    'PROJCS["MSK_77",GEOGCS["unknown",DATUM["Unknown based on Bessel 1841 ellipsoid",SPHEROID["Bessel 1841",6377397.155,299.1528128],TOWGS84[458.475,0.244,603.087,-3.98169,-0.43293,4.43381,1.713]],PRIMEM["Greenwich",0,AUTHORITY["EPSG","8901"]],UNIT["degree",0.0174532925199433,AUTHORITY["EPSG","9122"]]],PROJECTION["Transverse_Mercator"],PARAMETER["latitude_of_origin",55.66666666667],PARAMETER["central_meridian",37.5],PARAMETER["scale_factor",1],PARAMETER["false_easting",0],PARAMETER["false_northing",0],UNIT["metre",1,AUTHORITY["EPSG","9001"]],AXIS["Easting",EAST],AXIS["Northing",NORTH]]'
) ON CONFLICT (srid) DO NOTHING;

CREATE TABLE IF NOT EXISTS odh_export.ogh_analiz (
    id                          bigint PRIMARY KEY,
    "RootId"                    bigint,
    "ObjectId"                  bigint,
    "CustomerLegalPersonId"     bigint,
    "DepartmentLegalPersonId"   bigint,
    "CreateType"                text,
    "Name"                      text,
    "Landscaping"               text,
    "Geometry"                  geometry(MultiPolygon, 4326),
    "Link"                      text,
    "Type"                      text,
    "order"                     text,
    "DateSurvey"                timestamp without time zone,
    "StartDate"                 timestamp without time zone,
    "BrId"                      bigint,
    "PassportizationYear"       bigint,
    "OrderName"                 text,
    "OghStatus"                 text,
    "DepartmentWork"            text,
    itp_cr                      character varying(200),
    url                         character varying(4000),
    "GUID"                      uuid,
    loaded_at                   timestamptz NOT NULL DEFAULT NOW(),
    ozn_date                    date,
    executor                    text,
    status                      text
);

-- Local-only fields (not in gis.ogh_analiz / ATTR_COLUMNS). Kept across nightly sync.
ALTER TABLE odh_export.ogh_analiz
    ADD COLUMN IF NOT EXISTS ozn_date date,
    ADD COLUMN IF NOT EXISTS executor text,
    ADD COLUMN IF NOT EXISTS status text;

CREATE UNIQUE INDEX IF NOT EXISTS ux_ogh_analiz_ordername
    ON odh_export.ogh_analiz ("OrderName");

CREATE INDEX IF NOT EXISTS idx_ogh_analiz_geometry
    ON odh_export.ogh_analiz USING GIST ("Geometry");

CREATE INDEX IF NOT EXISTS idx_ogh_analiz_rootid
    ON odh_export.ogh_analiz ("RootId");
