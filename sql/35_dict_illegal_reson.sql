-- Dictionary: illegal work reason names.

CREATE SCHEMA IF NOT EXISTS dict;

CREATE TABLE IF NOT EXISTS dict.illegal_reson (
    id   SERIAL PRIMARY KEY,
    name TEXT NOT NULL UNIQUE
);

INSERT INTO dict.illegal_reson (name) VALUES
    ('Проведение земляных работ без оформленного ордера/уведомления (разрешения) ОАТИ'),
    ('Проведение работ после окончания срока действия ордера/уведомлении'),
    ('Несоответствие фактических работ целям, видам и типам, указанным в ордере/уведомлении'),
    ('Отсутствие информационного щита на строительной площадке (или его несоответствие требованиям)'),
    ('Отсутствие технического заключения ОПС (о соответствии проектной документации Сводному плану подземных коммуникаций)')
ON CONFLICT (name) DO NOTHING;
