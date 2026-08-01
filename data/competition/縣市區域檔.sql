-- public.sys_county definition

-- Drop table

-- DROP TABLE sys_county;

CREATE TABLE sys_county ( code varchar(2) NOT NULL, "name" varchar(10) NOT NULL, sort int4 NOT NULL, is_deleted varchar(2) NOT NULL, upd_time timestamptz NOT NULL, cre_time timestamptz NOT NULL, upd_id uuid NULL, cre_id uuid NOT NULL, CONSTRAINT sys_county_pkey PRIMARY KEY (code));
COMMENT ON TABLE public.sys_county IS '縣市代碼檔';

-- Column comments

COMMENT ON COLUMN public.sys_county.code IS '縣市代碼';
COMMENT ON COLUMN public.sys_county."name" IS '縣市名稱';
COMMENT ON COLUMN public.sys_county.sort IS '排序';
COMMENT ON COLUMN public.sys_county.is_deleted IS '0->正常；1->刪除';
COMMENT ON COLUMN public.sys_county.upd_time IS '異動日期時間';
COMMENT ON COLUMN public.sys_county.cre_time IS '新增日期時間';


-- public.sys_district definition

-- Drop table

-- DROP TABLE sys_district;

CREATE TABLE sys_district ( code varchar(3) NOT NULL, county_code varchar(2) NOT NULL, "name" varchar(20) NOT NULL, name_with_county varchar(20) NOT NULL, zip varchar(6) NOT NULL, sort int4 NOT NULL, is_deleted varchar(2) NOT NULL, upd_time timestamptz NOT NULL, cre_time timestamptz NOT NULL, upd_id uuid NULL, cre_id uuid NOT NULL, CONSTRAINT sys_district_pkey PRIMARY KEY (code));
COMMENT ON TABLE public.sys_district IS '行政區代碼檔';

-- Column comments

COMMENT ON COLUMN public.sys_district.code IS '行政區代碼';
COMMENT ON COLUMN public.sys_district.county_code IS '縣市代碼';
COMMENT ON COLUMN public.sys_district."name" IS '行政區名稱';
COMMENT ON COLUMN public.sys_district.name_with_county IS '行政區名稱和縣市名稱';
COMMENT ON COLUMN public.sys_district.zip IS '郵遞區號';
COMMENT ON COLUMN public.sys_district.sort IS '排序';
COMMENT ON COLUMN public.sys_district.is_deleted IS '0->正常；1->刪除';
COMMENT ON COLUMN public.sys_district.upd_time IS '異動日期時間';
COMMENT ON COLUMN public.sys_district.cre_time IS '新增日期時間';