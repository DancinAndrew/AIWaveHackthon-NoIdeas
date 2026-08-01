-- public.mms_order_record definition

-- Drop table

-- DROP TABLE public.mms_order_record;

CREATE TABLE public.mms_order_record (
	record_id bigserial NOT NULL, 
	order_no varchar(50) NOT NULL,
	service_vendor_id int4 NOT NULL,
	service_id int4 NOT NULL, 
	platform_code varchar(2) NOT NULL, 
	inbr_account_id uuid NOT NULL, 
	member_name bytea NULL, 
	member_name_hash varchar(50) NULL, 
	member_phone bytea NULL, 
	member_phone_hash varchar(50) NULL, 
	member_email bytea NULL, 
	member_email_hash varchar(50) NULL, 
	order_type varchar(2) NOT NULL, 
	order_status varchar(2) NOT NULL, 
	order_time timestamptz NOT NULL, 
	deposit_time timestamptz NULL, 
	confirm_time timestamptz NULL, 
	service_time timestamptz NULL, 
	complete_time timestamptz NULL, 
	cancel_time timestamptz NULL, 
	deposit_amount numeric(10, 2) DEFAULT 0 NOT NULL, 
	original_amount numeric(10, 2) DEFAULT 0 NOT NULL, 
	discount_amount numeric(10, 2) DEFAULT 0 NOT NULL, 
	shipping_fee_amount numeric(10, 2) DEFAULT 0 NOT NULL, 
	final_amount numeric(10, 2) DEFAULT 0 NOT NULL, 
	refund_amount numeric(10, 2) DEFAULT 0 NOT NULL, 
	order_points numeric(10, 2) DEFAULT 0 NOT NULL, 
	used_points numeric(10, 2) DEFAULT 0 NOT NULL, 
	refund_points numeric(10, 2) DEFAULT 0 NOT NULL, 
	earn_points numeric(10, 2) DEFAULT 0 NOT NULL, 
	point_status varchar(2) DEFAULT '01'::character varying NOT NULL, 
	point_grant_time timestamptz NULL, 
	vendor_data jsonb NULL, 
	order_items jsonb NULL, 
	remark text NULL, 
	cancel_reason text NULL, 
	refund_reason text NULL, 
	source_file varchar(200) NULL, 
	import_batch varchar(50) NULL, 
	quote_approved_by uuid NULL, 
	quote_approved_time timestamptz NULL, 
	quote_no varchar(64) NULL, 
	comment_status varchar(2) DEFAULT '00'::character varying NOT NULL, 
	is_deleted bool DEFAULT false NOT NULL,
	cre_id uuid NOT NULL, 
	cre_time timestamptz DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	upd_id uuid NOT NULL, 
	upd_time timestamptz DEFAULT CURRENT_TIMESTAMP NOT NULL, 
	CONSTRAINT pk_order_record PRIMARY KEY (record_id),
	CONSTRAINT uk_order_no_service UNIQUE (order_no, service_id)
);
CREATE INDEX idx_order_record_complete_time ON public.mms_order_record USING btree (complete_time);
CREATE INDEX idx_order_record_import_batch ON public.mms_order_record USING btree (import_batch);
CREATE INDEX idx_order_record_member ON public.mms_order_record USING btree (inbr_account_id);
CREATE INDEX idx_order_record_order_items ON public.mms_order_record USING gin (order_items);
CREATE INDEX idx_order_record_order_no ON public.mms_order_record USING btree (order_no);
CREATE INDEX idx_order_record_order_no_include1 ON public.mms_order_record USING btree (order_no, inbr_account_id) INCLUDE (record_id);
CREATE INDEX idx_order_record_order_status ON public.mms_order_record USING btree (record_id, order_status);
CREATE INDEX idx_order_record_order_time ON public.mms_order_record USING btree (order_time);
CREATE INDEX idx_order_record_platform ON public.mms_order_record USING btree (platform_code);
CREATE INDEX idx_order_record_point_process ON public.mms_order_record USING btree (point_status, order_status, complete_time);
CREATE INDEX idx_order_record_service ON public.mms_order_record USING btree (service_id);
CREATE INDEX idx_order_record_vendor_data ON public.mms_order_record USING gin (vendor_data);
COMMENT ON TABLE public.mms_order_record IS '訂單/訂位統一紀錄表，接收所有服務商的交易資料';

-- Column comments

COMMENT ON COLUMN public.mms_order_record.record_id IS '系統內部ID，自動遞增';
COMMENT ON COLUMN public.mms_order_record.order_no IS '訂單/訂位編號，服務商提供的唯一編號';
COMMENT ON COLUMN public.mms_order_record.service_vendor_id IS '服務提供商ID';
COMMENT ON COLUMN public.mms_order_record.service_id IS '服務ID';
COMMENT ON COLUMN public.mms_order_record.platform_code IS '平台代號，01:OP APP';
COMMENT ON COLUMN public.mms_order_record.inbr_account_id IS '會員編號uuid';
COMMENT ON COLUMN public.mms_order_record.member_name IS '會員姓名';
COMMENT ON COLUMN public.mms_order_record.member_name_hash IS '會員姓名hash';
COMMENT ON COLUMN public.mms_order_record.member_phone IS '會員電話密文';
COMMENT ON COLUMN public.mms_order_record.member_phone_hash IS '會員手機號碼hash';
COMMENT ON COLUMN public.mms_order_record.member_email IS '會員Email密文';
COMMENT ON COLUMN public.mms_order_record.member_email_hash IS '會員Email hash';
COMMENT ON COLUMN public.mms_order_record.order_type IS '訂單類型，01:服務訂單, 02:訂位, 03:預約, 04:其他,05:商品訂單,06訂餐';
COMMENT ON COLUMN public.mms_order_record.order_status IS '訂單狀態，依據訂單類型使用：
【01:服務訂單】使用：
11:待訂金支付,12:已支付訂金，待報價,13:已報價，待客戶同意,14:客戶同意報價,15:已驗收，待尾款支付
80:已完成, 90:已取消,98:部分退款,99:已退款

【 02:訂位】使用：
01:待付款,02:待確認, 03:已確認, 04:進行中,70:已完成(預定時間後3小時), 80:已完成(7天後核銷), 90:已取消, 99:已退款

【 03:預約, 04:其他,05:商品訂單,06:訂餐】使用：
01:待付款,02:待確認, 03:已確認, 04:進行中, 80:已完成, 90:已取消, 99:已退款

COMMENT ON COLUMN public.mms_order_record.order_time IS '訂單建立時間';
COMMENT ON COLUMN public.mms_order_record.deposit_time IS '訂金支付時間';
COMMENT ON COLUMN public.mms_order_record.confirm_time IS '確認時間';
COMMENT ON COLUMN public.mms_order_record.service_time IS '服務/使用時間';
COMMENT ON COLUMN public.mms_order_record.complete_time IS '完成時間，用於判斷點數發放時機';
COMMENT ON COLUMN public.mms_order_record.cancel_time IS '取消時間';
COMMENT ON COLUMN public.mms_order_record.deposit_amount IS '訂金金額';
COMMENT ON COLUMN public.mms_order_record.original_amount IS '原始金額';
COMMENT ON COLUMN public.mms_order_record.discount_amount IS '折扣金額';
COMMENT ON COLUMN public.mms_order_record.shipping_fee_amount IS '運費金額';
COMMENT ON COLUMN public.mms_order_record.final_amount IS '實付金額，作為點數計算基礎';
COMMENT ON COLUMN public.mms_order_record.refund_amount IS '退款金額';
COMMENT ON COLUMN public.mms_order_record.order_points IS '點數費用(訂單點數使用)';
COMMENT ON COLUMN public.mms_order_record.used_points IS '使用點數折抵金額';
COMMENT ON COLUMN public.mms_order_record.refund_points IS '退回點數';
COMMENT ON COLUMN public.mms_order_record.earn_points IS '應獲得點數，由點數計算引擎填入';
COMMENT ON COLUMN public.mms_order_record.point_status IS '點數發放狀態，01:待發放, 02:已發放, 03:不發放, 04:已取消';
COMMENT ON COLUMN public.mms_order_record.point_grant_time IS '點數發放時間';
COMMENT ON COLUMN public.mms_order_record.vendor_data IS '服務商特定欄位，JSON格式儲存各服務商的特殊資料';
COMMENT ON COLUMN public.mms_order_record.order_items IS '訂單項目明細，JSON陣列格式';
COMMENT ON COLUMN public.mms_order_record.remark IS '備註說明';
COMMENT ON COLUMN public.mms_order_record.cancel_reason IS '取消原因';
COMMENT ON COLUMN public.mms_order_record.refund_reason IS '退款原因';
COMMENT ON COLUMN public.mms_order_record.source_file IS '來源檔案名稱，用於追蹤資料來源';
COMMENT ON COLUMN public.mms_order_record.import_batch IS '匯入批次號，格式建議: YYYYMMDD_HHmmss_ServiceID';
COMMENT ON COLUMN public.mms_order_record.quote_approved_by IS '報價審核者編號';
COMMENT ON COLUMN public.mms_order_record.quote_approved_time IS '報價審核時間';
COMMENT ON COLUMN public.mms_order_record.quote_no IS '報價單no';
COMMENT ON COLUMN public.mms_order_record.comment_status IS '評價狀態，00:無須評價,01:未評價, 02:已評價';
COMMENT ON COLUMN public.mms_order_record.is_deleted IS '是否刪除';
COMMENT ON COLUMN public.mms_order_record.cre_id IS '新增者編號';
COMMENT ON COLUMN public.mms_order_record.cre_time IS '新增日期時間';
COMMENT ON COLUMN public.mms_order_record.upd_id IS '異動者編號';
COMMENT ON COLUMN public.mms_order_record.upd_time IS '異動日期時間';
