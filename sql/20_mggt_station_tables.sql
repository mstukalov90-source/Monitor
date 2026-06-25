-- MGGT station topo tables (KGS/SPS points and lines), modeled on topopassport.topopoint.

CREATE EXTENSION IF NOT EXISTS postgis;

-- Moscow MGGT (MSK-77) local CRS — required for geometry(..., 980077).
DELETE FROM spatial_ref_sys WHERE srid = 980077;
INSERT INTO spatial_ref_sys (srid, auth_name, auth_srid, proj4text, srtext)
VALUES (
    980077,
    'MSK_77',
    980077,
    '+proj=tmerc +lat_0=55.66666666667 +lon_0=37.5 +k=1 +x_0=0 +y_0=0 +ellps=bessel +towgs84=458.475,0.244,603.087,-3.98169,-0.43293,4.43381,1.713 +units=m +no_defs',
    'PROJCS["MSK_77",GEOGCS["unknown",DATUM["Unknown based on Bessel 1841 ellipsoid",SPHEROID["Bessel 1841",6377397.155,299.1528128],TOWGS84[458.475,0.244,603.087,-3.98169,-0.43293,4.43381,1.713]],PRIMEM["Greenwich",0,AUTHORITY["EPSG","8901"]],UNIT["degree",0.0174532925199433,AUTHORITY["EPSG","9122"]]],PROJECTION["Transverse_Mercator"],PARAMETER["latitude_of_origin",55.66666666667],PARAMETER["central_meridian",37.5],PARAMETER["scale_factor",1],PARAMETER["false_easting",0],PARAMETER["false_northing",0],UNIT["metre",1,AUTHORITY["EPSG","9001"]],AXIS["Easting",EAST],AXIS["Northing",NORTH]]'
);

CREATE SCHEMA IF NOT EXISTS mggt_station;

CREATE TABLE IF NOT EXISTS mggt_station.kgs_point (
    fid serial4 NOT NULL,
    "text" text NULL,
    "name" text NULL,
    layer text NULL,
    ocolor text NULL,
    olinetype text NULL,
    angle text NULL,
    weight text NULL,
    guid uuid NULL,
    "Number" text NULL,
    datesurvey timestamp NULL,
    "Geometry" public.geometry(point, 980077) NULL,
    "BasePolyUsage" bool DEFAULT true NULL,
    CONSTRAINT kgs_point_pkey PRIMARY KEY (fid)
);

CREATE INDEX IF NOT EXISTS kgs_point_Geom_idx
    ON mggt_station.kgs_point USING gist ("Geometry");
CREATE INDEX IF NOT EXISTS kgs_point_guid_idx
    ON mggt_station.kgs_point USING btree (guid);

CREATE TABLE IF NOT EXISTS mggt_station.sps_point (
    fid serial4 NOT NULL,
    "text" text NULL,
    "name" text NULL,
    layer text NULL,
    ocolor text NULL,
    olinetype text NULL,
    angle text NULL,
    weight text NULL,
    guid uuid NULL,
    "Number" text NULL,
    datesurvey timestamp NULL,
    "Geometry" public.geometry(point, 980077) NULL,
    "BasePolyUsage" bool DEFAULT true NULL,
    CONSTRAINT sps_point_pkey PRIMARY KEY (fid)
);

CREATE INDEX IF NOT EXISTS sps_point_Geom_idx
    ON mggt_station.sps_point USING gist ("Geometry");
CREATE INDEX IF NOT EXISTS sps_point_guid_idx
    ON mggt_station.sps_point USING btree (guid);

CREATE TABLE IF NOT EXISTS mggt_station.kgs_lines (
    fid serial4 NOT NULL,
    "text" text NULL,
    "name" text NULL,
    layer text NULL,
    ocolor text NULL,
    olinetype text NULL,
    angle text NULL,
    weight text NULL,
    guid uuid NULL,
    "Number" text NULL,
    datesurvey timestamp NULL,
    "Geometry" public.geometry(Geometry, 980077) NULL,
    "BasePolyUsage" bool DEFAULT true NULL,
    CONSTRAINT kgs_lines_pkey PRIMARY KEY (fid)
);

CREATE INDEX IF NOT EXISTS kgs_lines_Geom_idx
    ON mggt_station.kgs_lines USING gist ("Geometry");
CREATE INDEX IF NOT EXISTS kgs_lines_guid_idx
    ON mggt_station.kgs_lines USING btree (guid);

CREATE TABLE IF NOT EXISTS mggt_station.sps_lines (
    fid serial4 NOT NULL,
    "text" text NULL,
    "name" text NULL,
    layer text NULL,
    ocolor text NULL,
    olinetype text NULL,
    angle text NULL,
    weight text NULL,
    guid uuid NULL,
    "Number" text NULL,
    datesurvey timestamp NULL,
    "Geometry" public.geometry(Geometry, 980077) NULL,
    "BasePolyUsage" bool DEFAULT true NULL,
    CONSTRAINT sps_lines_pkey PRIMARY KEY (fid)
);

CREATE INDEX IF NOT EXISTS sps_lines_Geom_idx
    ON mggt_station.sps_lines USING gist ("Geometry");
CREATE INDEX IF NOT EXISTS sps_lines_guid_idx
    ON mggt_station.sps_lines USING btree (guid);
