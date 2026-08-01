"""種子資料：廠商 + demo 會員。

廠商刻意讓每家有不同強項（價格 / 速度 / 品牌專精 / 女性技師 / 保固），
這樣媒合 agent 的排序才有意義，demo 也才看得出差異。

台北市 = 01（001 中正 002 大同 003 中山 004 萬華 005 信義 006 松山 007 大安
             008 南港 009 北投 010 內湖 011 士林 012 文山）
新北市 = 02（013 板橋 024 汐止 030 新店 033 中和 034 永和 039 三重 040 蘆洲 041 五股 ...）
完整清單見 geo_generated.py
"""

from __future__ import annotations

from .domain import UserProfile, Vendor

SEED_VENDORS: list[Vendor] = [
    {
        "vendorId": "V001",
        "name": "冷研家電維修工作室",
        "serviceVendorId": 11,
        "categories": ["AC_REPAIR", "AC_CLEAN"],
        "coverage": [
            {"countyCode": "01", "districtCodes": "ALL"},
            {"countyCode": "02", "districtCodes": ["013", "033", "034", "039"]},
        ],
        "rating": 4.9,
        "reviewCount": 428,
        "completedJobs": 1620,
        "avgResponseMinutes": 12,
        "earliestAvailableInDays": 1,
        "availableSlots": ["1", "2"],
        "tags": ["當日到府", "原廠零件", "保固一年", "日系品牌專精"],
        "pricing": {
            "inspectionFee": 600,
            "items": [
                {"code": "AC_GAS", "name": "冷媒填充（R32/R410a）", "minPrice": 1800, "maxPrice": 3200},
                {"code": "AC_LEAK", "name": "排水管堵塞疏通 / 漏水處理", "minPrice": 1200, "maxPrice": 2400},
                {"code": "AC_PCB", "name": "室內機控制板更換", "minPrice": 3500, "maxPrice": 6800},
                {"code": "AC_FAN", "name": "風扇馬達更換", "minPrice": 2800, "maxPrice": 5200},
                {"code": "AC_COMP", "name": "壓縮機更換", "minPrice": 9800, "maxPrice": 18000},
            ],
        },
        "certifications": ["甲級冷凍空調技術士"],
        "supportsPoints": True,
    },
    {
        "vendorId": "V002",
        "name": "安心水電空調",
        "serviceVendorId": 11,
        "categories": ["AC_REPAIR", "PLUMBING"],
        "coverage": [
            {"countyCode": "01", "districtCodes": ["001", "002", "003", "004", "006", "011"]},
            {"countyCode": "02", "districtCodes": ["039", "040", "041"]},
        ],
        "rating": 4.5,
        "reviewCount": 213,
        "completedJobs": 890,
        "avgResponseMinutes": 35,
        "earliestAvailableInDays": 2,
        "availableSlots": ["1", "2", "3"],
        "tags": ["價格實惠", "水電一併處理", "現金折扣"],
        "pricing": {
            "inspectionFee": 350,
            "items": [
                {"code": "AC_GAS", "name": "冷媒填充", "minPrice": 1500, "maxPrice": 2600},
                {"code": "AC_LEAK", "name": "排水管堵塞疏通 / 漏水處理", "minPrice": 900, "maxPrice": 1800},
                {"code": "AC_PCB", "name": "室內機控制板更換", "minPrice": 3000, "maxPrice": 5800},
                {"code": "AC_FAN", "name": "風扇馬達更換", "minPrice": 2400, "maxPrice": 4600},
                {"code": "AC_COMP", "name": "壓縮機更換", "minPrice": 8800, "maxPrice": 16000},
            ],
        },
        "certifications": ["乙級冷凍空調技術士", "室內配線技術士"],
        "supportsPoints": True,
    },
    {
        "vendorId": "V003",
        "name": "潔淨女子家事修繕隊",
        "serviceVendorId": 11,
        "categories": ["AC_REPAIR", "AC_CLEAN", "HOME_CLEAN"],
        "coverage": [
            {"countyCode": "01", "districtCodes": ["005", "006", "007", "008", "010", "012"]},
        ],
        "rating": 4.8,
        "reviewCount": 356,
        "completedJobs": 1104,
        "avgResponseMinutes": 20,
        "earliestAvailableInDays": 3,
        "availableSlots": ["1", "2"],
        "tags": ["女性技師", "獨居友善", "穿鞋套", "清潔一併處理"],
        "pricing": {
            "inspectionFee": 500,
            "items": [
                {"code": "AC_GAS", "name": "冷媒填充", "minPrice": 1900, "maxPrice": 3000},
                {"code": "AC_LEAK", "name": "排水管堵塞疏通 / 漏水處理", "minPrice": 1100, "maxPrice": 2200},
                {
                    "code": "AC_CLEAN",
                    "name": "分離式冷氣深層清洗",
                    "minPrice": 1600,
                    "maxPrice": 2600,
                    "unit": "台",
                },
                {"code": "AC_PCB", "name": "室內機控制板更換", "minPrice": 3600, "maxPrice": 6500},
            ],
        },
        "certifications": ["乙級冷凍空調技術士"],
        "supportsPoints": True,
    },
    {
        "vendorId": "V004",
        "name": "極速到府空調急修",
        "serviceVendorId": 11,
        "categories": ["AC_REPAIR"],
        "coverage": [
            {"countyCode": "01", "districtCodes": "ALL"},
            {"countyCode": "02", "districtCodes": "ALL"},
        ],
        "rating": 4.2,
        "reviewCount": 189,
        "completedJobs": 2310,
        "avgResponseMinutes": 6,
        "earliestAvailableInDays": 0,
        "availableSlots": ["1", "2", "3"],
        "tags": ["2 小時到府", "24 小時服務", "假日不加價"],
        "pricing": {
            "inspectionFee": 900,
            "items": [
                {"code": "AC_GAS", "name": "冷媒填充", "minPrice": 2200, "maxPrice": 3800},
                {"code": "AC_LEAK", "name": "排水管堵塞疏通 / 漏水處理", "minPrice": 1500, "maxPrice": 2800},
                {"code": "AC_PCB", "name": "室內機控制板更換", "minPrice": 4200, "maxPrice": 7500},
                {"code": "AC_FAN", "name": "風扇馬達更換", "minPrice": 3200, "maxPrice": 5800},
                {"code": "AC_COMP", "name": "壓縮機更換", "minPrice": 11000, "maxPrice": 20000},
            ],
        },
        "supportsPoints": False,
    },
    {
        "vendorId": "V005",
        "name": "大金／日立原廠協力站",
        "serviceVendorId": 11,
        "categories": ["AC_REPAIR"],
        "coverage": [
            {"countyCode": "01", "districtCodes": "ALL"},
            {"countyCode": "02", "districtCodes": ["013", "024", "030", "033", "034"]},
        ],
        "rating": 4.7,
        "reviewCount": 512,
        "completedJobs": 3050,
        "avgResponseMinutes": 48,
        "earliestAvailableInDays": 4,
        "availableSlots": ["1", "2"],
        "tags": ["原廠零件", "保固兩年", "大金專精", "日立專精", "吊隱式可處理"],
        "pricing": {
            "inspectionFee": 800,
            "items": [
                {"code": "AC_GAS", "name": "冷媒填充（原廠規格）", "minPrice": 2400, "maxPrice": 3600},
                {"code": "AC_LEAK", "name": "排水管堵塞疏通 / 漏水處理", "minPrice": 1400, "maxPrice": 2600},
                {"code": "AC_PCB", "name": "室內機控制板更換（原廠）", "minPrice": 4800, "maxPrice": 8800},
                {"code": "AC_FAN", "name": "風扇馬達更換（原廠）", "minPrice": 3600, "maxPrice": 6400},
                {"code": "AC_COMP", "name": "壓縮機更換（原廠）", "minPrice": 12000, "maxPrice": 22000},
            ],
        },
        "certifications": ["原廠授權服務站", "甲級冷凍空調技術士"],
        "supportsPoints": True,
    },
    {
        "vendorId": "V006",
        "name": "新北好厝邊修繕行",
        "serviceVendorId": 11,
        "categories": ["AC_REPAIR", "PLUMBING"],
        "coverage": [{"countyCode": "02", "districtCodes": "ALL"}],
        "rating": 4.4,
        "reviewCount": 97,
        "completedJobs": 520,
        "avgResponseMinutes": 55,
        "earliestAvailableInDays": 2,
        "availableSlots": ["1", "2", "3"],
        "tags": ["價格實惠", "在地老師傅", "長者友善"],
        "pricing": {
            "inspectionFee": 300,
            "items": [
                {"code": "AC_GAS", "name": "冷媒填充", "minPrice": 1400, "maxPrice": 2400},
                {"code": "AC_LEAK", "name": "排水管堵塞疏通 / 漏水處理", "minPrice": 800, "maxPrice": 1600},
                {"code": "AC_PCB", "name": "室內機控制板更換", "minPrice": 2800, "maxPrice": 5400},
                {"code": "AC_FAN", "name": "風扇馬達更換", "minPrice": 2200, "maxPrice": 4200},
            ],
        },
        "supportsPoints": False,
    },
]

# 症狀 -> 可能的維修項目代碼，讓報價估算有依據
SYMPTOM_TO_ITEMS: dict[str, list[str]] = {
    "不冷": ["AC_GAS", "AC_COMP"],
    "不夠冷": ["AC_GAS", "AC_CLEAN"],
    "漏水": ["AC_LEAK"],
    "滴水": ["AC_LEAK"],
    "異音": ["AC_FAN"],
    "噪音": ["AC_FAN"],
    "不啟動": ["AC_PCB", "AC_COMP"],
    "沒反應": ["AC_PCB"],
    "跳電": ["AC_PCB", "AC_COMP"],
    "遙控無反應": ["AC_PCB"],
    "有異味": ["AC_CLEAN"],
    "結冰": ["AC_GAS", "AC_CLEAN"],
}

# Demo 會員。inbrAccountId 沿用命題數據集裡的 uuid（pms_form_feedback.inbr_account_id）
DEMO_USER_ID = "019a52d3-7f6b-7a51-a53a-3c365f741b49"

SEED_USERS: list[UserProfile] = [
    {
        "inbrAccountId": DEMO_USER_ID,
        "displayName": "陳小美",
        "mobile": "0935777888",
        "email": "demo@openpoint.example",
        "points": 1280,
        "addresses": [
            {
                "countyCode": "01",
                "countyName": "台北市",
                "districtCode": "007",
                "districtName": "大安區",
                "detail": "復興南路一段 100 號 5 樓",
            },
            {
                "countyCode": "02",
                "countyName": "新北市",
                "districtCode": "013",
                "districtName": "板橋區",
                "detail": "文化路二段 20 號（爸媽家）",
            },
        ],
        "appliances": [
            {
                "applianceId": "A1",
                "kind": "AC",
                "brand": "大金",
                "variant": "分離式",
                "installedYear": 2018,
                "location": "主臥",
            },
            {
                "applianceId": "A2",
                "kind": "AC",
                "brand": "日立",
                "variant": "窗型",
                "installedYear": 2014,
                "location": "客廳",
            },
            {"applianceId": "A3", "kind": "WASHER", "brand": "LG", "installedYear": 2021},
        ],
        # 真實情境是由歷史訂單（mms_order_record）+ 對話累積算出來的，
        # 這裡放初始值，agent 每次對話會持續往上疊加
        "preferences": {
            "priceSensitivity": 0.6,
            "preferredContactTime": "2",
            "preferredVendorTags": ["原廠零件", "保固一年"],
            "interestedCategories": ["AC_CLEAN", "HOME_CLEAN"],
            "blockedVendorIds": [],
            "notes": ["過去偏好假日以外時段", "曾反映不喜歡被推銷加購"],
        },
    },
]
