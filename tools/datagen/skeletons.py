"""需求 skeleton：先產生結構化答案，句子之後才由 utterances 反向組出來。

案件資料與評測集共用同一組 skeleton，確保兩邊的欄位語彙完全一致。
"""

from __future__ import annotations

from datetime import timedelta

import vocab
from common import D_DAY, iso

# 各類必填欄位（對齊 openspec contracts/forms/*.schema.json）
REQUIRED_FIELDS = {
    "restaurant_reservation": [
        "contact.name", "contact.mobile", "preferred_contact_time", "consent",
        "restaurant.location", "restaurant.reservation_at", "restaurant.party_size",
        "restaurant.cuisine_preferences", "restaurant.budget_per_person",
    ],
    "product_purchase": [
        "contact.name", "contact.mobile", "preferred_contact_time", "consent",
        "product.query", "product.category", "product.budget", "product.quantity",
        "product.delivery", "product.accept_substitutes",
    ],
    "housekeeping_service": [
        "contact.name", "contact.mobile", "preferred_contact_time", "consent",
        "housekeeping.service_items", "housekeeping.property_type", "housekeeping.location",
        "housekeeping.preferred_time_slots", "housekeeping.frequency", "housekeeping.has_pets",
    ],
    "utility_repair": [
        "contact.name", "contact.mobile", "preferred_contact_time", "consent",
        "repair.issue_type", "repair.symptoms", "repair.location", "repair.urgency",
        "repair.hazard_flags", "repair.preferred_time_slots",
    ],
    "community_consultation": [
        "contact.name", "contact.mobile", "preferred_contact_time", "consent",
        "community.community_name", "community.location", "community.issue_category",
        "community.description", "community.urgency", "community.anonymity_preference",
    ],
}

FREQUENCY_TEXT = {
    "one_time": "只做這一次",
    "weekly": "每週一次",
    "biweekly": "兩週一次",
    "monthly": "每月一次",
}
TIME_TEXT = {"morning": "上午", "afternoon": "下午", "evening": "晚上", "any": "都可以"}

# 各品類的合理單價帶，供需求端預算取樣
CATEGORY_BUDGET = {
    "家電": (1500, 20000),
    "生活用品": (80, 700),
    "食品飲料": (100, 1400),
    "母嬰": (200, 2600),
    "寵物": (150, 3000),
    "3C周邊": (250, 5000),
    "居家修繕": (60, 2000),
    "運動戶外": (200, 2400),
}

REPAIR_SYMPTOMS = {
    "leak": ["天花板一直滴水", "牆壁滲水發霉", "水管接頭在漏水", "陽台牆面有水痕擴散"],
    "plumbing": ["水壓很小幾乎沒水", "水龍頭關不緊一直滴", "熱水出不來"],
    "electrical": ["插座沒電", "跳電跳個不停", "電燈一直閃"],
    "water_heater": ["熱水器點不著", "洗澡水忽冷忽熱", "熱水器一直發出怪聲"],
    "toilet": ["馬桶沖水沖不乾淨", "馬桶水箱一直漏水", "馬桶堵住了"],
    "drain": ["浴室排水很慢", "廚房水槽塞住", "陽台排水孔回堵有臭味"],
    "other": ["門鎖卡住打不開", "紗窗脫軌", "抽風機不轉了"],
}
COMMUNITY_DESCRIPTIONS = {
    "public_facility": ["中庭的路燈壞了三盞已經一個月", "健身房跑步機故障沒人修"],
    "noise": ["樓上半夜一直有拖椅子的聲音", "隔壁裝潢從早上七點就開始施工"],
    "parking": ["有人長期佔用訪客車位", "地下室機車亂停擋住通道"],
    "waste": ["資源回收室滿出來沒人清", "垃圾車時間改了但公告沒貼"],
    "security": ["大門磁扣感應常常失效", "門口有陌生人尾隨進入"],
    "elevator": ["電梯昨天卡在四樓有人受困", "電梯門開關會夾人"],
    "leak_dispute": ["樓上浴室漏水滲到我家天花板", "外牆滲水影響到兩戶"],
    "fee_dispute": ["管理費調漲沒有開會通知", "帳目公告已經三個月沒更新"],
    "pet": ["有住戶在公共區域放狗不牽繩", "狗吠聲影響到鄰居"],
    "renovation": ["想申請裝修但不知道要準備什麼", "施工電梯保護要怎麼安排"],
}
AFFECTED_AREAS = ["中庭", "地下二樓停車場", "B 棟一樓大廳", "頂樓平台", "電梯前室", "資源回收室"]
WHEN_STARTED = ["昨天晚上", "前天", "上禮拜", "今天早上", "大概半個月前"]

URGENCY_INDEX = {"routine": 0, "soon": 1, "urgent": 2, "emergency": 3}

# 只有這些故障類型才可能出現對應危險徵兆，避免「紗窗脫軌但有冒煙」這種矛盾
HAZARDS_BY_ISSUE = {
    "electrical": ["electric_shock_risk", "exposed_wires", "smoke_or_burning_smell"],
    "water_heater": ["gas_smell", "smoke_or_burning_smell"],
    "leak": ["active_flooding", "electric_shock_risk"],
    "plumbing": ["active_flooding"],
    "toilet": ["active_flooding"],
    "drain": ["active_flooding"],
}
# 設備必須和故障類型相符
ASSETS_BY_ISSUE = {
    "electrical": ["配電箱", "插座", "照明迴路"],
    "water_heater": ["熱水器"],
    "leak": ["水管", "浴室天花板"],
    "plumbing": ["水龍頭", "洗手台"],
    "toilet": ["馬桶"],
    "drain": ["排水管"],
    "other": ["紗窗", "門鎖", "抽風機"],
}


def _time_text(hour: int) -> str:
    if hour < 11:
        return f"早上{hour}點"
    if hour < 13:
        return f"中午{hour}點"
    if hour < 18:
        return f"下午{hour - 12}點"
    return f"晚上{hour - 12}點"

STYLES = ["polite", "polite", "terse", "rambling", "voice_typo"]


def pick_style(random_source) -> str:
    return random_source.choice(STYLES)


def make(service_type: str, index: int, random_source, geo: dict) -> dict:
    """產生一筆完整（所有必填都有值）的 skeleton。"""
    district = geo["pick_district"](random_source, service_type, index)
    slot_dt = D_DAY + timedelta(
        days=random_source.randint(1, 18), hours=random_source.choice([10, 13, 15, 18, 19])
    )
    date_text = f"{slot_dt.month}/{slot_dt.day} "
    contact_pref = random_source.choice(vocab.CONTACT_TIME_PREFS)

    builder = {
        "restaurant_reservation": _restaurant,
        "product_purchase": _product,
        "housekeeping_service": _housekeeping,
        "utility_repair": _repair,
        "community_consultation": _community,
    }[service_type]

    fields, fragments = builder(random_source, district, slot_dt, date_text, geo)
    fields["preferred_contact_time"] = contact_pref
    fields["contact.name"] = "{{CONTACT_NAME}}"
    fields["contact.mobile"] = "{{CONTACT_MOBILE}}"
    fields["consent"] = {"privacy_policy_version": "2026-01", "accepted": True}

    return {
        "skeleton_id": f"sk-{service_type.split('_')[0]}-{index:04d}",
        "service_type": service_type,
        "district": district,
        "fields": fields,
        "fragments": fragments,
        "style": pick_style(random_source),
        "slot_at": iso(slot_dt),
    }


def _loc_slots(district: dict) -> dict:
    return {"county": district["county_name"], "district": district["name"]}


def _restaurant(random_source, district, slot_dt, date_text, geo):
    cuisine = random_source.choice(vocab.CUISINES)
    party_size = random_source.choice([2, 2, 3, 4, 4, 6, 8, 10, 12])
    budget = random_source.choice([300, 500, 800, 1200, 1500, 2500])
    dietary = random_source.choice(vocab.DIETARY_SUPPORTS)
    seating = random_source.choice(vocab.SEATING_TYPES)
    children = random_source.randint(1, 3)
    time_text = _time_text(slot_dt.hour)

    fields = {
        "restaurant.location": {"county_code": district["county_code"], "district_code": district["district_code"]},
        "restaurant.reservation_at": iso(slot_dt),
        "restaurant.party_size": party_size,
        "restaurant.cuisine_preferences": [cuisine],
        "restaurant.budget_per_person": budget,
    }
    fragments = {
        "location": _loc_slots(district),
        "reservation_at": {"date_text": date_text, "time_text": time_text},
        "party_size": {"party_size": party_size},
        "cuisine": {"cuisine": cuisine},
        "budget": {"budget": f"{budget}元"},
    }
    if random_source.random() < 0.35:
        fields["restaurant.dietary_restrictions"] = [dietary]
        fragments["dietary"] = {"dietary": dietary}
    if random_source.random() < 0.3:
        fields["restaurant.seating_preference"] = seating
        fragments["seating"] = {"seating": seating}
    if random_source.random() < 0.25:
        fields["restaurant.children_count"] = children
        fragments["children"] = {"children": children}
    return fields, fragments


def _product(random_source, district, slot_dt, date_text, geo):
    category = random_source.choice(list(vocab.PRODUCT_CATEGORIES))
    item = random_source.choice(vocab.PRODUCT_CATEGORIES[category])
    quantity = random_source.choice([1, 1, 2, 3, 5, 10])
    brand = random_source.choice(vocab.PRODUCT_BRANDS)
    accept_substitutes = random_source.random() < 0.7
    # 預算貼著該品項在 SKU 目錄的中位價，避免「濕紙巾預算 12000」這種組合
    unit_price = geo["item_price"].get(item) or sum(CATEGORY_BUDGET[category]) // 2
    budget = int(round(unit_price * quantity * random_source.uniform(0.8, 1.6) / 50) * 50)

    fields = {
        "product.query": item,
        "product.category": category,
        "product.budget": budget,
        "product.quantity": quantity,
        "product.delivery": {
            "county_code": district["county_code"],
            "district_code": district["district_code"],
            "deadline": iso(slot_dt),
        },
        "product.accept_substitutes": accept_substitutes,
    }
    fragments = {
        "query": {"item": item},
        "category": {"category": category},
        "budget": {"budget": f"{budget}元"},
        "quantity": {"quantity": quantity},
        "delivery": _loc_slots(district),
        "deadline": {"deadline": date_text.strip()},
        "substitute": {"__pick__": random_source.randint(0, 1) if accept_substitutes else 2},
    }
    if random_source.random() < 0.4:
        fields["product.brand_preferences"] = [brand]
        fragments["brand"] = {"brand": brand}
    return fields, fragments


def _housekeeping(random_source, district, slot_dt, date_text, geo):
    items = random_source.sample(vocab.HOUSEKEEPING_ITEMS, k=random_source.randint(1, 3))
    property_type = random_source.choice(vocab.PROPERTY_TYPES)
    area = random_source.choice([8, 12, 18, 25, 32, 45, 60])
    frequency = random_source.choice(vocab.CLEAN_FREQUENCIES)
    has_pets = random_source.random() < 0.35
    time_text = TIME_TEXT[random_source.choice(["morning", "afternoon", "evening"])]

    fields = {
        "housekeeping.service_items": [i["code"] for i in items],
        "housekeeping.property_type": property_type,
        "housekeeping.location": {"county_code": district["county_code"], "district_code": district["district_code"]},
        "housekeeping.preferred_time_slots": [iso(slot_dt)],
        "housekeeping.frequency": frequency,
        "housekeeping.has_pets": has_pets,
    }
    fragments = {
        "service_items": {"items": "、".join(i["label"] for i in items)},
        "property_type": {"property_type": property_type},
        "location": _loc_slots(district),
        "time": {"date_text": date_text, "time_text": time_text},
        "frequency": {"frequency_text": FREQUENCY_TEXT[frequency]},
        "pets": {"__pick__": random_source.randint(0, 1) if has_pets else 2},
    }
    if random_source.random() < 0.5:
        fields["housekeeping.area_sqm"] = area
        fragments["area"] = {"area": area}
    if random_source.random() < 0.3:
        fields["housekeeping.photos"] = ["{{PHOTO_REF_1}}"]
        fragments["photos"] = {}
    return fields, fragments


def _repair(random_source, district, slot_dt, date_text, geo):
    issue = random_source.choice(vocab.REPAIR_ISSUE_TYPES)
    symptom = random_source.choice(REPAIR_SYMPTOMS[issue["code"]])
    urgency = random_source.choice(vocab.URGENCY_LEVELS)
    hazards = {flag: False for flag in vocab.HAZARD_FLAGS}
    possible_hazards = HAZARDS_BY_ISSUE.get(issue["code"], [])
    if possible_hazards and (urgency == "emergency" or random_source.random() < 0.22):
        hazards[random_source.choice(possible_hazards)] = True
        urgency = "emergency"
    elif urgency == "emergency" and not possible_hazards:
        # 這類故障不會有危險徵兆，降一級避免「emergency 但沒有任何風險」
        urgency = "urgent"
    time_text = TIME_TEXT[random_source.choice(["morning", "afternoon", "evening"])]

    fields = {
        "repair.issue_type": issue["code"],
        "repair.symptoms": symptom,
        "repair.location": {"county_code": district["county_code"], "district_code": district["district_code"]},
        "repair.urgency": urgency,
        "repair.hazard_flags": hazards,
        "repair.preferred_time_slots": [iso(slot_dt)],
    }
    fragments = {
        "symptom": {"symptom": symptom, "when_started": random_source.choice(WHEN_STARTED)},
        "issue_type": {"issue_label": issue["label"]},
        "location": _loc_slots(district),
        "urgency": {"__pick__": URGENCY_INDEX[urgency]},
        "time": {"date_text": date_text, "time_text": time_text},
    }
    if any(hazards.values()):
        fragments["hazard"] = hazards
    if random_source.random() < 0.4:
        asset = random_source.choice(ASSETS_BY_ISSUE[issue["code"]])
        brand = random_source.choice(vocab.PRODUCT_BRANDS)
        age = random_source.randint(1, 20)
        fields["repair.asset_type"] = asset
        fields["repair.asset_brand"] = brand
        fields["repair.asset_age_years"] = age
        fragments["asset"] = {"asset": asset, "brand": brand, "age": age}
    if random_source.random() < 0.35:
        fields["repair.photos"] = ["{{PHOTO_REF_1}}"]
        fragments["photos"] = {}
    return fields, fragments


def _community(random_source, district, slot_dt, date_text, geo):
    community = geo["pick_community"](random_source, district)
    category = random_source.choice(vocab.COMMUNITY_ISSUE_CATEGORIES)
    description = random_source.choice(COMMUNITY_DESCRIPTIONS[category["code"]])
    urgency = random_source.choice(vocab.URGENCY_LEVELS)
    anonymity = random_source.choice(["named", "anonymous_to_neighbors", "anonymous"])

    fields = {
        "community.community_name": community["name"],
        "community.location": {"county_code": district["county_code"], "district_code": district["district_code"]},
        "community.issue_category": category["code"],
        "community.description": description,
        "community.urgency": urgency,
        "community.anonymity_preference": anonymity,
    }
    fragments = {
        "community": {"community": community["name"]},
        "issue": {"issue_label": category["label"]},
        "description": {"description": description},
        "location": _loc_slots(district),
        "urgency": {"__pick__": URGENCY_INDEX[urgency]},
        "anonymity": {"__pick__": 2 if anonymity == "named" else random_source.randint(0, 1)},
    }
    if random_source.random() < 0.4:
        area = random_source.choice(AFFECTED_AREAS)
        fields["community.affected_area"] = area
        fragments["affected_area"] = {"affected_area": area}
    if random_source.random() < 0.3:
        fields["community.attachments"] = ["{{ATTACHMENT_REF_1}}"]
        fragments["attachment"] = {}
    return fields, fragments
