"""合成資料的詞庫與領域常數。全部虛構，不對應真實店家。"""

from __future__ import annotations

# ---------------------------------------------------------------- 服務覆蓋設定

# 主檔密集覆蓋的縣市（六都 + 基隆 / 新竹市 / 宜蘭）
DENSE_COUNTIES = ["01", "02", "04", "08", "14", "15", "03", "06", "17"]
# 稀疏覆蓋：每縣市只有 1~2 家服務商
SPARSE_COUNTIES = ["05", "07", "09", "10", "11", "12", "13", "16", "18", "19"]
# 刻意留白：完全沒有服務商，用來驗證 unmatched 與放寬建議
BLANK_COUNTIES = ["20", "21", "22"]

# ------------------------------------------------------------------- 餐廳訂位

CUISINES = [
    "台式熱炒", "日式料理", "義式料理", "粵菜港點", "韓式燒肉",
    "泰式料理", "法式餐酒", "素食蔬食", "火鍋", "美式漢堡",
]

RESTAURANT_NAME_PARTS = {
    "台式熱炒": ["樂多", "阿川", "老四川", "巷口", "海線"],
    "日式料理": ["初魚", "藏壽司", "和居", "旬彩", "六花"],
    "義式料理": ["Trattoria 小巷", "橄欖樹", "Pasta Piu", "米蘭諾", "灶咖"],
    "粵菜港點": ["點點心", "翠園", "添好味", "港龍軒", "金滿樓"],
    "韓式燒肉": ["姜虎東", "肉倉", "首爾夜", "豚道", "韓江"],
    "泰式料理": ["泰街角", "湄南河", "香茅屋", "曼谷小館", "打拋"],
    "法式餐酒": ["Le Petit", "布列塔尼", "銀盤", "Chez Wu", "夜巴黎"],
    "素食蔬食": ["禪食", "綠芽", "蔬適", "淨月", "一畝田"],
    "火鍋": ["涮八方", "石頭鍋", "麻辣殿", "湯屋", "鍋鍋"],
    "美式漢堡": ["Burger Lab", "肉多多", "Route66", "老美式", "雙層"],
}
RESTAURANT_SUFFIXES = ["餐廳", "食堂", "館", "小館", "料理"]

SEATING_TYPES = ["一般座位", "包廂", "吧台", "戶外座位"]
DIETARY_SUPPORTS = ["素食", "全素", "無麩質", "海鮮過敏調整", "清真", "低鈉"]
RESERVATION_CANCEL_RULES = [
    {"code": "free_24h", "label": "訂位前 24 小時可免費取消，逾時不退訂金"},
    {"code": "free_48h", "label": "訂位前 48 小時可免費取消，逾時扣 50% 訂金"},
    {"code": "no_deposit", "label": "不收訂金，未到場累計 2 次將暫停線上訂位"},
    {"code": "strict", "label": "訂金恕不退還，可改期一次"},
]

# ------------------------------------------------------------------- 商品購買

PRODUCT_CATEGORIES = {
    "家電": ["除濕機", "空氣清淨機", "電風扇", "電鍋", "掃地機器人", "吸塵器"],
    "生活用品": ["洗衣精", "衛生紙", "垃圾袋", "收納箱", "除臭劑"],
    "食品飲料": ["咖啡豆", "麥片", "調理包", "礦泉水", "堅果"],
    "母嬰": ["紙尿褲", "濕紙巾", "奶瓶", "副食品調理機"],
    "寵物": ["貓砂", "狗飼料", "寵物零食", "自動餵食器"],
    "3C周邊": ["行動電源", "USB-C 傳輸線", "藍牙耳機", "機械鍵盤", "螢幕支架"],
    "居家修繕": ["矽利康", "水管接頭", "LED 燈泡", "工具組", "門把"],
    "運動戶外": ["瑜珈墊", "登山水壺", "護膝", "跳繩"],
}
PRODUCT_BRANDS = [
    "禾聯", "聲寶", "大同", "小澤", "宜家生活", "米樂", "藍鵲",
    "友柏", "綠芽", "InnoHome", "DailyPlus", "Nordika",
]
DELIVERY_METHODS = [
    {"code": "home_delivery", "label": "宅配到府", "days": 3, "fee": 120, "free_over": 990},
    {"code": "cvs_pickup", "label": "超商取貨", "days": 4, "fee": 60, "free_over": 490},
    {"code": "same_day", "label": "當日速配", "days": 0, "fee": 180, "free_over": 2000},
    {"code": "large_item", "label": "大型商品專車", "days": 7, "fee": 400, "free_over": 9999},
]
RETURN_POLICIES = [
    {"code": "standard_7d", "label": "到貨 7 日內未拆封可退貨，運費由買方負擔"},
    {"code": "free_return_7d", "label": "到貨 7 日內免費退貨，platform 負擔運費"},
    {"code": "food_no_return", "label": "食品類拆封後不可退，僅接受瑕疵換貨"},
    {"code": "appliance_15d", "label": "家電 15 日保固換新，之後轉原廠維修"},
]

# ------------------------------------------------------------------- 家事服務

HOUSEKEEPING_ITEMS = [
    {"code": "regular_clean", "label": "一般居家清潔", "pricing": "hourly", "unit": "小時", "price": 450},
    {"code": "deep_clean", "label": "深度清潔", "pricing": "per_ping", "unit": "坪", "price": 180},
    {"code": "move_in_clean", "label": "入厝/退租清潔", "pricing": "per_ping", "unit": "坪", "price": 260},
    {"code": "kitchen_clean", "label": "廚房重油污清潔", "pricing": "fixed", "unit": "式", "price": 2800},
    {"code": "bathroom_clean", "label": "浴室除霉清潔", "pricing": "fixed", "unit": "間", "price": 1600},
    {"code": "aircon_split", "label": "分離式冷氣清洗", "pricing": "per_unit", "unit": "台", "price": 2500},
    {"code": "aircon_window", "label": "窗型冷氣清洗", "pricing": "per_unit", "unit": "台", "price": 1800},
    {"code": "washer_clean", "label": "洗衣機清洗", "pricing": "per_unit", "unit": "台", "price": 2100},
    {"code": "fridge_clean", "label": "冰箱清洗", "pricing": "per_unit", "unit": "台", "price": 2200},
    {"code": "window_clean", "label": "窗戶紗窗清潔", "pricing": "per_unit", "unit": "扇", "price": 350},
    {"code": "laundry_fold", "label": "洗衣摺衣", "pricing": "hourly", "unit": "小時", "price": 400},
    {"code": "cooking", "label": "到府備餐", "pricing": "hourly", "unit": "小時", "price": 550},
]
PROPERTY_TYPES = ["公寓", "電梯大樓", "透天厝", "套房", "辦公室"]
HOUSEKEEPING_SKILLS = [
    "pet_friendly", "eco_supplies", "own_supplies", "elderly_care_experience",
    "english_speaking", "night_shift", "weekend_available", "heavy_duty_kitchen",
]
CLEAN_FREQUENCIES = ["one_time", "weekly", "biweekly", "monthly"]

# ------------------------------------------------------------------- 水電修繕

REPAIR_ISSUE_TYPES = [
    {"code": "plumbing", "label": "給排水管線"},
    {"code": "electrical", "label": "電路配線"},
    {"code": "water_heater", "label": "熱水器"},
    {"code": "toilet", "label": "馬桶"},
    {"code": "drain", "label": "排水阻塞"},
    {"code": "leak", "label": "漏水"},
    {"code": "other", "label": "其他"},
]
REPAIR_CERTIFICATIONS = [
    "甲種電匠", "乙種電匠", "室內配線技術士", "自來水管配管技術士",
    "冷凍空調技術士", "特定瓦斯器具裝修技術士", "用電設備檢驗維護業技術員",
]
REPAIR_CAPABILITIES = [
    "emergency_24h", "night_shift", "weekend_available", "leak_detection",
    "gas_certified", "high_voltage", "old_building_experience",
    "apartment_riser_pipe", "waterproofing", "same_day_dispatch",
]
HAZARD_FLAGS = [
    "electric_shock_risk", "exposed_wires", "smoke_or_burning_smell",
    "active_flooding", "gas_smell",
]

# --------------------------------------------------------------- 社區服務諮詢

COMMUNITY_ISSUE_CATEGORIES = [
    {"code": "public_facility", "label": "公共設施損壞"},
    {"code": "noise", "label": "噪音糾紛"},
    {"code": "parking", "label": "停車與車位管理"},
    {"code": "waste", "label": "垃圾清運與資源回收"},
    {"code": "security", "label": "門禁與保全"},
    {"code": "elevator", "label": "電梯故障"},
    {"code": "leak_dispute", "label": "樓上樓下漏水糾紛"},
    {"code": "fee_dispute", "label": "管理費爭議"},
    {"code": "pet", "label": "寵物飼養規約"},
    {"code": "renovation", "label": "裝修施工申請"},
]
RESPONSIBLE_UNIT_TYPES = [
    {"code": "management_committee", "label": "社區管理委員會"},
    {"code": "property_management", "label": "物業管理公司"},
    {"code": "city_service_1999", "label": "縣市民服務專線"},
    {"code": "building_authority", "label": "地方建管單位"},
    {"code": "environment_bureau", "label": "環保局"},
]
COMMUNITY_NAME_PARTS = [
    "文華", "青田", "翠堤", "康橋", "德明", "永康", "松江", "潤泰",
    "麗景", "書香", "海悅", "遠雄", "都心", "綠園", "禾風",
]
COMMUNITY_NAME_SUFFIXES = ["社區", "大廈", "花園廣場", "首馥", "官邸", "名邸"]

# -------------------------------------------------------------------- 共用

SERVICE_TYPES = [
    "restaurant_reservation",
    "product_purchase",
    "housekeeping_service",
    "utility_repair",
    "community_consultation",
]
SERVICE_TYPE_LABELS = {
    "restaurant_reservation": "餐廳訂位",
    "product_purchase": "商品購買",
    "housekeeping_service": "家事服務",
    "utility_repair": "水電修繕",
    "community_consultation": "社區服務諮詢",
}
URGENCY_LEVELS = ["routine", "soon", "urgent", "emergency"]
CONTACT_TIME_PREFS = ["morning", "afternoon", "evening", "any"]
