-- ============================================================================
-- OpenPoint 生活管家 — 商家與客戶資料 schema
--
-- 命名沿用統一資訊命題資料集的風格：
--   sys_*  系統代碼檔（縣市、行政區）—— 直接對應他們給的 sys_county / sys_district
--   mms_*  會員與商家主檔        —— 對應 mms_order_record 的 mms 前綴
--   欄位一律 snake_case、時間用 timestamptz、刪除註記用 varchar(2) '0'/'1'
--
-- 這支 SQL 是「可重跑的」（idempotent）：每次執行會先砍掉舊表再重建。
-- 開發階段這樣最省事，但正式環境絕對不能這樣做（會清掉真實資料）。
-- ============================================================================

-- 依賴關係反序刪除，否則 foreign key 會擋
DROP TABLE IF EXISTS mms_member_preference CASCADE;
DROP TABLE IF EXISTS mms_member_appliance CASCADE;
DROP TABLE IF EXISTS mms_member_address CASCADE;
DROP TABLE IF EXISTS mms_member CASCADE;
DROP TABLE IF EXISTS mms_vendor_pricing_item CASCADE;
DROP TABLE IF EXISTS mms_vendor_coverage CASCADE;
DROP TABLE IF EXISTS mms_vendor CASCADE;
DROP TABLE IF EXISTS sys_district CASCADE;
DROP TABLE IF EXISTS sys_county CASCADE;


-- ============================================================================
-- 1. 系統代碼檔（來源：統一資訊「縣市區域範例資料.json」）
-- ============================================================================

CREATE TABLE sys_county (
    code        varchar(2)  NOT NULL,           -- 縣市代碼，如 '01'
    name        varchar(10) NOT NULL,           -- 縣市名稱，如 '台北市'
    sort        int4        NOT NULL DEFAULT 0,
    is_deleted  varchar(2)  NOT NULL DEFAULT '0',
    cre_time    timestamptz NOT NULL DEFAULT now(),
    upd_time    timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT sys_county_pkey PRIMARY KEY (code)
);
COMMENT ON TABLE sys_county IS '縣市代碼檔';

CREATE TABLE sys_district (
    code        varchar(3)  NOT NULL,           -- 行政區代碼，如 '007'
    county_code varchar(2)  NOT NULL,           -- 所屬縣市
    name        varchar(20) NOT NULL,           -- 行政區名稱，如 '大安區'
    zip         varchar(6),                     -- 郵遞區號
    sort        int4        NOT NULL DEFAULT 0,
    is_deleted  varchar(2)  NOT NULL DEFAULT '0',
    cre_time    timestamptz NOT NULL DEFAULT now(),
    upd_time    timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT sys_district_pkey PRIMARY KEY (code),
    CONSTRAINT sys_district_county_fkey FOREIGN KEY (county_code) REFERENCES sys_county (code)
);
COMMENT ON TABLE sys_district IS '行政區代碼檔';
CREATE INDEX idx_sys_district_county ON sys_district (county_code);


-- ============================================================================
-- 2. 商家（服務廠商）
-- ============================================================================

CREATE TABLE mms_vendor (
    vendor_id                  varchar(16)  NOT NULL,   -- 'V001'
    name                       varchar(100) NOT NULL,
    service_vendor_id          int4         NOT NULL,   -- 對應 cms_homepage_service_vendor.id（11=修繕服務）
    categories                 text[]       NOT NULL,   -- {'AC_REPAIR','AC_CLEAN'}
    rating                     numeric(2,1) NOT NULL DEFAULT 0,   -- 0.0 ~ 5.0
    review_count               int4         NOT NULL DEFAULT 0,
    completed_jobs             int4         NOT NULL DEFAULT 0,
    avg_response_minutes       int4         NOT NULL DEFAULT 0,   -- 平均回應分鐘
    earliest_available_in_days int4         NOT NULL DEFAULT 0,   -- 最快幾天後可到府
    available_slots            varchar(2)[] NOT NULL,   -- {'1','2'} 1上午 2下午 3皆可
    tags                       text[]       NOT NULL DEFAULT '{}',
    certifications             text[]       NOT NULL DEFAULT '{}',
    inspection_fee             int4         NOT NULL DEFAULT 0,   -- 到府檢測費
    supports_points            boolean      NOT NULL DEFAULT false,
    is_enable                  varchar(2)   NOT NULL DEFAULT '1',
    is_deleted                 varchar(2)   NOT NULL DEFAULT '0',
    cre_time                   timestamptz  NOT NULL DEFAULT now(),
    upd_time                   timestamptz  NOT NULL DEFAULT now(),
    CONSTRAINT mms_vendor_pkey PRIMARY KEY (vendor_id),
    CONSTRAINT mms_vendor_rating_chk CHECK (rating >= 0 AND rating <= 5)
);
COMMENT ON TABLE mms_vendor IS '服務廠商主檔';
COMMENT ON COLUMN mms_vendor.available_slots IS '可服務時段：1 上午 2 下午 3 皆可';

-- 商家服務區域：一家廠商對多個行政區，所以是獨立一張表
CREATE TABLE mms_vendor_coverage (
    vendor_id     varchar(16) NOT NULL,
    county_code   varchar(2)  NOT NULL,
    district_code varchar(3),                   -- NULL = 該縣市全區都服務
    cre_time      timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT mms_vendor_coverage_vendor_fkey FOREIGN KEY (vendor_id)
        REFERENCES mms_vendor (vendor_id) ON DELETE CASCADE,
    CONSTRAINT mms_vendor_coverage_county_fkey FOREIGN KEY (county_code)
        REFERENCES sys_county (code),
    CONSTRAINT mms_vendor_coverage_district_fkey FOREIGN KEY (district_code)
        REFERENCES sys_district (code)
);
COMMENT ON TABLE mms_vendor_coverage IS '廠商服務區域檔；district_code 為 NULL 表示該縣市全區服務';
CREATE INDEX idx_vendor_coverage_area ON mms_vendor_coverage (county_code, district_code);
CREATE INDEX idx_vendor_coverage_vendor ON mms_vendor_coverage (vendor_id);

-- 商家價目表：報價引擎的資料來源
CREATE TABLE mms_vendor_pricing_item (
    id         bigserial    NOT NULL,
    vendor_id  varchar(16)  NOT NULL,
    item_code  varchar(20)  NOT NULL,           -- 'AC_GAS' / 'AC_COMP' ...
    item_name  varchar(100) NOT NULL,
    min_price  int4         NOT NULL,
    max_price  int4         NOT NULL,
    unit       varchar(20),
    is_major   boolean      NOT NULL DEFAULT false,  -- 大額項目（如壓縮機），報價要獨立揭露
    cre_time   timestamptz  NOT NULL DEFAULT now(),
    CONSTRAINT mms_vendor_pricing_item_pkey PRIMARY KEY (id),
    CONSTRAINT mms_vendor_pricing_item_vendor_fkey FOREIGN KEY (vendor_id)
        REFERENCES mms_vendor (vendor_id) ON DELETE CASCADE,
    CONSTRAINT mms_vendor_pricing_uk UNIQUE (vendor_id, item_code),
    CONSTRAINT mms_vendor_pricing_range_chk CHECK (min_price <= max_price)
);
COMMENT ON TABLE mms_vendor_pricing_item IS '廠商價目表；is_major 的項目不計入主報價區間，需獨立揭露';
CREATE INDEX idx_vendor_pricing_item_code ON mms_vendor_pricing_item (item_code);


-- ============================================================================
-- 3. 客戶（會員）
--
-- 注意 PII：統一資訊的 pms_form_feedback 是「密文 bytea + hash varchar」雙欄位
-- 設計（aes256-gcm 加密存內容、hash 用來做等值查詢）。
-- 這裡先用明文欄位，但把 *_hash 欄位預留出來，之後要補加密不用改表結構。
-- ============================================================================

CREATE TABLE mms_member (
    inbr_account_id uuid         NOT NULL,      -- 對應 mms_order_record.inbr_account_id
    display_name    varchar(50)  NOT NULL,
    mobile          varchar(20),                -- TODO 正式環境改 bytea 密文
    mobile_hash     varchar(64),                -- 供等值查詢用
    email           varchar(100),
    email_hash      varchar(64),
    points          int4         NOT NULL DEFAULT 0,
    is_deleted      varchar(2)   NOT NULL DEFAULT '0',
    cre_time        timestamptz  NOT NULL DEFAULT now(),
    upd_time        timestamptz  NOT NULL DEFAULT now(),
    CONSTRAINT mms_member_pkey PRIMARY KEY (inbr_account_id)
);
COMMENT ON TABLE mms_member IS '會員主檔';
COMMENT ON COLUMN mms_member.mobile IS '手機號碼。正式環境須改為 aes256-gcm 密文（見 pms_form_feedback 做法）';
CREATE INDEX idx_member_mobile_hash ON mms_member (mobile_hash);

CREATE TABLE mms_member_address (
    id              bigserial    NOT NULL,
    inbr_account_id uuid         NOT NULL,
    label           varchar(30),                -- '住家' / '爸媽家'
    county_code     varchar(2)   NOT NULL,
    district_code   varchar(3)   NOT NULL,
    detail          varchar(200),               -- TODO 正式環境改 bytea 密文
    detail_hash     varchar(64),
    is_default      boolean      NOT NULL DEFAULT false,
    cre_time        timestamptz  NOT NULL DEFAULT now(),
    CONSTRAINT mms_member_address_pkey PRIMARY KEY (id),
    CONSTRAINT mms_member_address_member_fkey FOREIGN KEY (inbr_account_id)
        REFERENCES mms_member (inbr_account_id) ON DELETE CASCADE,
    CONSTRAINT mms_member_address_county_fkey FOREIGN KEY (county_code)
        REFERENCES sys_county (code),
    CONSTRAINT mms_member_address_district_fkey FOREIGN KEY (district_code)
        REFERENCES sys_district (code)
);
COMMENT ON TABLE mms_member_address IS '會員常用地址檔';
CREATE INDEX idx_member_address_member ON mms_member_address (inbr_account_id);
CREATE INDEX idx_member_address_area ON mms_member_address (county_code, district_code);

-- 家電清單：讓 agent 不用每次問「你家冷氣什麼牌子、幾年了」
CREATE TABLE mms_member_appliance (
    id              bigserial    NOT NULL,
    inbr_account_id uuid         NOT NULL,
    appliance_id    varchar(16)  NOT NULL,      -- 'A1'
    kind            varchar(20)  NOT NULL,      -- 'AC' / 'WASHER' / 'FRIDGE' / 'WATER_HEATER'
    brand           varchar(50),
    model           varchar(50),
    variant         varchar(30),                -- 分離式 / 窗型 / 吊隱式
    installed_year  int4,
    location        varchar(30),                -- '主臥' / '客廳'
    cre_time        timestamptz  NOT NULL DEFAULT now(),
    CONSTRAINT mms_member_appliance_pkey PRIMARY KEY (id),
    CONSTRAINT mms_member_appliance_member_fkey FOREIGN KEY (inbr_account_id)
        REFERENCES mms_member (inbr_account_id) ON DELETE CASCADE,
    CONSTRAINT mms_member_appliance_uk UNIQUE (inbr_account_id, appliance_id)
);
COMMENT ON TABLE mms_member_appliance IS '會員家電清單，agent 用來免除重複詢問';
CREATE INDEX idx_member_appliance_member ON mms_member_appliance (inbr_account_id);

-- 偏好：一個會員一列，用 jsonb 存陣列型偏好（標籤、筆記）
-- 為什麼混用欄位與 jsonb？數值型偏好會進 SQL 運算（排序加權），所以獨立成欄位；
-- 標籤與筆記只是讀出來給 agent 看，用 jsonb 最有彈性。
CREATE TABLE mms_member_preference (
    inbr_account_id       uuid         NOT NULL,
    price_sensitivity     numeric(3,2) NOT NULL DEFAULT 0.50,  -- 0.00 不在意 ~ 1.00 非常在意
    preferred_contact_time varchar(2),                          -- 1 上午 2 下午 3 皆可
    preferred_vendor_tags jsonb        NOT NULL DEFAULT '[]',
    blocked_vendor_ids    jsonb        NOT NULL DEFAULT '[]',
    interested_categories jsonb        NOT NULL DEFAULT '[]',
    notes                 jsonb        NOT NULL DEFAULT '[]',
    upd_time              timestamptz  NOT NULL DEFAULT now(),
    CONSTRAINT mms_member_preference_pkey PRIMARY KEY (inbr_account_id),
    CONSTRAINT mms_member_preference_member_fkey FOREIGN KEY (inbr_account_id)
        REFERENCES mms_member (inbr_account_id) ON DELETE CASCADE,
    CONSTRAINT mms_member_preference_sens_chk CHECK (price_sensitivity >= 0 AND price_sensitivity <= 1)
);
COMMENT ON TABLE mms_member_preference IS '會員偏好檔，媒合加權與自動推播的依據';


-- ============================================================================
-- 4. 方便查詢的 view：把商家服務區域攤平成好讀的樣子
-- ============================================================================

CREATE OR REPLACE VIEW v_vendor_service_area AS
SELECT
    v.vendor_id,
    v.name           AS vendor_name,
    c.name           AS county_name,
    COALESCE(d.name, '全區') AS district_name,
    v.rating,
    v.inspection_fee
FROM mms_vendor v
JOIN mms_vendor_coverage cv ON cv.vendor_id = v.vendor_id
JOIN sys_county c           ON c.code = cv.county_code
LEFT JOIN sys_district d    ON d.code = cv.district_code
WHERE v.is_deleted = '0' AND v.is_enable = '1';

COMMENT ON VIEW v_vendor_service_area IS '廠商 × 服務區域攤平檢視，人工核對資料時很好用';
