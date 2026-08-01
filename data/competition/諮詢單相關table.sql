-- public.pms_form definition

-- Drop table

-- DROP TABLE pms_form;

CREATE TABLE pms_form ( id serial4 NOT NULL, service_vendor_id int4 NOT NULL, "type" varchar(2) NOT NULL, sub_type varchar(2) NOT NULL, "name" varchar(50) NOT NULL, intro_content text NULL, notice_content text NULL, terms_content text NULL, review_status varchar(2) NOT NULL, reviewed_id uuid NULL, reviewed_time timestamptz NULL, is_enable varchar(2) NOT NULL, is_deleted varchar(2) NOT NULL, upd_time timestamptz NOT NULL, cre_time timestamptz NOT NULL, upd_id uuid NULL, cre_id uuid NOT NULL, feature jsonb NULL, CONSTRAINT pms_form_pkey PRIMARY KEY (id));
COMMENT ON TABLE public.pms_form IS '表單主檔';

-- Column comments

COMMENT ON COLUMN public.pms_form.id IS '流水號';
COMMENT ON COLUMN public.pms_form.service_vendor_id IS '服務提供商ID';
COMMENT ON COLUMN public.pms_form."type" IS '表單類型(1	C端客戶(無現場評估)2	C端客戶(需評估)3	B端客戶4	轉訂單流程5	客服';
COMMENT ON COLUMN public.pms_form.sub_type IS '表單子類型(1	一般表單 2	估價表單)';
COMMENT ON COLUMN public.pms_form."name" IS '表單名稱';
COMMENT ON COLUMN public.pms_form.intro_content IS '服務介紹頁面內容(html)';
COMMENT ON COLUMN public.pms_form.notice_content IS '注意事項頁面內容(html)';
COMMENT ON COLUMN public.pms_form.terms_content IS '服務條款(html)';
COMMENT ON COLUMN public.pms_form.review_status IS '審核狀態:0->未審核；1->已審核';
COMMENT ON COLUMN public.pms_form.reviewed_id IS '審核人員ID';
COMMENT ON COLUMN public.pms_form.reviewed_time IS '審核時間';
COMMENT ON COLUMN public.pms_form.is_enable IS '是否啟用:0->禁用；1->啟用';
COMMENT ON COLUMN public.pms_form.is_deleted IS '刪除註記:0->未刪除；1->已刪除';
COMMENT ON COLUMN public.pms_form.upd_time IS '異動日期時間';
COMMENT ON COLUMN public.pms_form.cre_time IS '新增日期時間';
COMMENT ON COLUMN public.pms_form.feature IS '擴充屬性(可以json內容定義不同呈現屬性)';


-- public.pms_form_feedback definition

-- Drop table

-- DROP TABLE pms_form_feedback;

CREATE TABLE pms_form_feedback ( feedback_no varchar(16) NOT NULL, service_id int4 NOT NULL, platform_code varchar(2) NOT NULL, form_id int4 NOT NULL, feedback_content jsonb NOT NULL, form_type varchar(2) NOT NULL, is_read varchar(2) NOT NULL, status varchar(2) NOT NULL, contact_name bytea NULL, contact_name_hash varchar(50) NULL, contact_mobile bytea NULL, contact_mobile_hash varchar(50) NULL, contact_landline bytea NULL, contact_landline_hash varchar(50) NULL, contact_email bytea NULL, contact_email_hash varchar(50) NULL, preferred_contact_time varchar(2) NULL, contact_address_county varchar(10) NULL, contact_address_district varchar(20) NULL, contact_address_detail bytea NULL, contact_address_detail_hash varchar(50) NULL, description varchar(1000) NULL, inbr_account_id uuid NOT NULL, cre_time timestamptz NOT NULL, upd_id uuid NULL, upd_time timestamptz NOT NULL, CONSTRAINT pms_form_feedback_pkey PRIMARY KEY (feedback_no));
COMMENT ON TABLE public.pms_form_feedback IS '表單回饋檔';

-- Column comments

COMMENT ON COLUMN public.pms_form_feedback.feedback_no IS '回饋單號';
COMMENT ON COLUMN public.pms_form_feedback.service_id IS '服務ID';
COMMENT ON COLUMN public.pms_form_feedback.platform_code IS '平台代號';
COMMENT ON COLUMN public.pms_form_feedback.form_id IS '表單ID';
COMMENT ON COLUMN public.pms_form_feedback.feedback_content IS '表單回饋內容';
COMMENT ON COLUMN public.pms_form_feedback.form_type IS '表單類型';
COMMENT ON COLUMN public.pms_form_feedback.is_read IS '是否已讀:0->未讀；1->已讀';
COMMENT ON COLUMN public.pms_form_feedback.status IS '回饋狀態';
COMMENT ON COLUMN public.pms_form_feedback.contact_name IS '聯絡人姓名(aes256 gcm加密)';
COMMENT ON COLUMN public.pms_form_feedback.contact_name_hash IS '聯絡人姓名hash';
COMMENT ON COLUMN public.pms_form_feedback.contact_mobile IS '聯絡人手機(aes256 gcm加密)';
COMMENT ON COLUMN public.pms_form_feedback.contact_mobile_hash IS '聯絡人手機hash';
COMMENT ON COLUMN public.pms_form_feedback.contact_landline IS '聯絡人市話(aes256 gcm加密)';
COMMENT ON COLUMN public.pms_form_feedback.contact_landline_hash IS '聯絡人市話hash';
COMMENT ON COLUMN public.pms_form_feedback.contact_email IS '聯絡人E-mail(aes256 gcm加密)';
COMMENT ON COLUMN public.pms_form_feedback.contact_email_hash IS '聯絡人E-mail hash';
COMMENT ON COLUMN public.pms_form_feedback.preferred_contact_time IS '方便聯絡時間(1	上午 2	下午 3	皆可)';
COMMENT ON COLUMN public.pms_form_feedback.contact_address_county IS '聯絡地址-縣市';
COMMENT ON COLUMN public.pms_form_feedback.contact_address_district IS '聯絡地址-行政區';
COMMENT ON COLUMN public.pms_form_feedback.contact_address_detail IS '聯絡地址-詳細地址(aes256 gcm加密)';
COMMENT ON COLUMN public.pms_form_feedback.contact_address_detail_hash IS '聯絡地址-詳細地址hash';
COMMENT ON COLUMN public.pms_form_feedback.description IS '備註';
COMMENT ON COLUMN public.pms_form_feedback.inbr_account_id IS '會員編號';
COMMENT ON COLUMN public.pms_form_feedback.cre_time IS '新增日期時間';
COMMENT ON COLUMN public.pms_form_feedback.upd_time IS '異動日期時間';


-- public.pms_form_group definition

-- Drop table

-- DROP TABLE pms_form_group;

CREATE TABLE pms_form_group ( id serial4 NOT NULL, form_id int4 NOT NULL, "name" varchar(50) NOT NULL, sort int4 NOT NULL, upd_time timestamptz NOT NULL, cre_time timestamptz NOT NULL, upd_id uuid NULL, cre_id uuid NOT NULL, feature jsonb NULL, CONSTRAINT pms_form_group_pkey PRIMARY KEY (id));
COMMENT ON TABLE public.pms_form_group IS '表單題組主檔';

-- Column comments

COMMENT ON COLUMN public.pms_form_group.id IS '流水號';
COMMENT ON COLUMN public.pms_form_group.form_id IS '表單ID';
COMMENT ON COLUMN public.pms_form_group."name" IS '題組名稱';
COMMENT ON COLUMN public.pms_form_group.sort IS '排序';
COMMENT ON COLUMN public.pms_form_group.upd_time IS '異動日期時間';
COMMENT ON COLUMN public.pms_form_group.cre_time IS '新增日期時間';
COMMENT ON COLUMN public.pms_form_group.feature IS '擴充屬性';


-- public.pms_form_topic definition

-- Drop table

-- DROP TABLE pms_form_topic;

CREATE TABLE pms_form_topic ( id serial4 NOT NULL, form_id int4 NOT NULL, form_group_id int4 NOT NULL, "type" varchar(2) NOT NULL, title varchar(200) NOT NULL, remark varchar(500) NULL, is_required varchar(2) NOT NULL, sort int4 NOT NULL, is_number_only varchar(2) NULL, minimum_medias_upload int4 NULL, maximum_medias_upload int4 NULL, specified_medias_upload int4 NULL, start_date_offset_days int4 NULL, end_date_offset_days int4 NULL, upd_time timestamptz NOT NULL, cre_time timestamptz NOT NULL, upd_id uuid NULL, cre_id uuid NOT NULL, feature jsonb NULL, CONSTRAINT pms_form_topic_pkey PRIMARY KEY (id));
COMMENT ON TABLE public.pms_form_topic IS '表單題目主檔';

-- Column comments

COMMENT ON COLUMN public.pms_form_topic.id IS '流水號';
COMMENT ON COLUMN public.pms_form_topic.form_id IS '表單ID';
COMMENT ON COLUMN public.pms_form_topic.form_group_id IS '表單題組ID';
COMMENT ON COLUMN public.pms_form_topic."type" IS '題目類別1	簡答題 2	詳答題 3	單選題 4	複選題 5	地區選單 6	上傳照片 7	備註說明 8	聯絡資料 9	日期題 10	聯絡資料(不含地址)';
COMMENT ON COLUMN public.pms_form_topic.title IS '題目名稱';
COMMENT ON COLUMN public.pms_form_topic.remark IS '題目說明';
COMMENT ON COLUMN public.pms_form_topic.is_required IS '必填設定:0->非必填；1->必填';
COMMENT ON COLUMN public.pms_form_topic.sort IS '題目排序';
COMMENT ON COLUMN public.pms_form_topic.is_number_only IS '(簡答題使用)只能輸入數字:0->未指定；1->指定數字';
COMMENT ON COLUMN public.pms_form_topic.minimum_medias_upload IS '(照片題)照片最少上傳數';
COMMENT ON COLUMN public.pms_form_topic.maximum_medias_upload IS '(照片題)照片最多上傳數';
COMMENT ON COLUMN public.pms_form_topic.specified_medias_upload IS '(照片題)照片指定上傳數';
COMMENT ON COLUMN public.pms_form_topic.start_date_offset_days IS '可選起日相對D日偏移天數';
COMMENT ON COLUMN public.pms_form_topic.end_date_offset_days IS '可選迄日相對D日偏移天數';
COMMENT ON COLUMN public.pms_form_topic.upd_time IS '異動日期時間';
COMMENT ON COLUMN public.pms_form_topic.cre_time IS '新增日期時間';
COMMENT ON COLUMN public.pms_form_topic.feature IS '擴充屬性';


-- public.pms_topic_media definition

-- Drop table

-- DROP TABLE pms_topic_media;

CREATE TABLE pms_topic_media ( id serial4 NOT NULL, form_id int4 NOT NULL, topic_id int4 NOT NULL, img_url text NOT NULL, sort int4 NOT NULL, upd_time timestamptz NOT NULL, cre_time timestamptz NOT NULL, upd_id uuid NULL, cre_id uuid NOT NULL, CONSTRAINT pms_topic_media_pkey PRIMARY KEY (id));
CREATE INDEX idx_pms_topic_media_form_id ON public.pms_topic_media USING btree (form_id);
CREATE INDEX idx_pms_topic_media_form_topic ON public.pms_topic_media USING btree (form_id, topic_id);
CREATE INDEX idx_pms_topic_media_topic_id ON public.pms_topic_media USING btree (topic_id);
COMMENT ON TABLE public.pms_topic_media IS '表單題目圖片檔';

-- Column comments

COMMENT ON COLUMN public.pms_topic_media.id IS '流水號';
COMMENT ON COLUMN public.pms_topic_media.form_id IS '表單ID';
COMMENT ON COLUMN public.pms_topic_media.topic_id IS '題目ID';
COMMENT ON COLUMN public.pms_topic_media.img_url IS '輔助說明圖片網址';
COMMENT ON COLUMN public.pms_topic_media.sort IS '排序';
COMMENT ON COLUMN public.pms_topic_media.upd_time IS '異動日期時間';
COMMENT ON COLUMN public.pms_topic_media.cre_time IS '新增日期時間';


-- public.pms_topic_option definition

-- Drop table

-- DROP TABLE pms_topic_option;

CREATE TABLE pms_topic_option ( id serial4 NOT NULL, form_id int4 NOT NULL, topic_id int4 NOT NULL, option_name varchar(200) NOT NULL, unit_price int4 NULL, unit varchar(30) NULL, is_quantity varchar(2) NULL, min_quantity int4 NULL, max_quantity int4 NULL, is_quoted_separately varchar(2) NULL, remark varchar(500) NULL, sort int4 NOT NULL, upd_time timestamptz NOT NULL, cre_time timestamptz NOT NULL, upd_id uuid NULL, cre_id uuid NOT NULL, feature jsonb NULL, CONSTRAINT pms_topic_option_pkey PRIMARY KEY (id));
COMMENT ON TABLE public.pms_topic_option IS '表單選項主檔 ';

-- Column comments

COMMENT ON COLUMN public.pms_topic_option.id IS '流水號';
COMMENT ON COLUMN public.pms_topic_option.form_id IS '表單ID';
COMMENT ON COLUMN public.pms_topic_option.topic_id IS '題目ID';
COMMENT ON COLUMN public.pms_topic_option.option_name IS '選項名稱';
COMMENT ON COLUMN public.pms_topic_option.unit_price IS '單價';
COMMENT ON COLUMN public.pms_topic_option.unit IS '單位';
COMMENT ON COLUMN public.pms_topic_option.is_quantity IS '數量可選:0->不可選；1->可選';
COMMENT ON COLUMN public.pms_topic_option.min_quantity IS '最小可選數量';
COMMENT ON COLUMN public.pms_topic_option.max_quantity IS '最大可選數量';
COMMENT ON COLUMN public.pms_topic_option.is_quoted_separately IS '是否為另行報價:0->否；1->是';
COMMENT ON COLUMN public.pms_topic_option.remark IS '選項說明';
COMMENT ON COLUMN public.pms_topic_option.sort IS '排序';
COMMENT ON COLUMN public.pms_topic_option.upd_time IS '異動日期時間';
COMMENT ON COLUMN public.pms_topic_option.cre_time IS '新增日期時間';
COMMENT ON COLUMN public.pms_topic_option.feature IS '擴充屬性';


-- public.pms_topic_county_district_relation definition

-- Drop table

-- DROP TABLE pms_topic_county_district_relation;

CREATE TABLE pms_topic_county_district_relation ( form_id int4 NOT NULL, topic_id int4 NOT NULL, eff_ts_from timestamptz NOT NULL, eff_ts_to timestamptz NOT NULL, county_code varchar(2) NOT NULL, district_code varchar(3) NOT NULL, upd_time timestamptz NOT NULL, cre_time timestamptz NOT NULL, upd_id uuid NULL, cre_id uuid NOT NULL, CONSTRAINT pms_topic_county_district_relation_pkey PRIMARY KEY (form_id, topic_id, eff_ts_from, county_code, district_code));
COMMENT ON TABLE public.pms_topic_county_district_relation IS '題目縣市行政區對應檔';

-- Column comments

COMMENT ON COLUMN public.pms_topic_county_district_relation.form_id IS '表單ID';
COMMENT ON COLUMN public.pms_topic_county_district_relation.topic_id IS '題目ID';
COMMENT ON COLUMN public.pms_topic_county_district_relation.eff_ts_from IS '適用日期時間起';
COMMENT ON COLUMN public.pms_topic_county_district_relation.eff_ts_to IS '適用日期時間迄';
COMMENT ON COLUMN public.pms_topic_county_district_relation.county_code IS '縣市代碼';
COMMENT ON COLUMN public.pms_topic_county_district_relation.district_code IS '行政區代碼';
COMMENT ON COLUMN public.pms_topic_county_district_relation.upd_time IS '異動日期時間';
COMMENT ON COLUMN public.pms_topic_county_district_relation.cre_time IS '新增日期時間';