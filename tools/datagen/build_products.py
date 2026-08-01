"""商品 SKU 主檔：規格、價格、庫存、配送、退換貨、促銷。"""

from __future__ import annotations

from datetime import timedelta

import vocab
from common import D_DAY, iso, read_mock, report, rng, stable_uuid, write_json

TARGET_SKU_COUNT = 300

SPEC_TEMPLATES = {
    "除濕機": [("容量", ["6L/日", "10L/日", "12L/日", "16L/日"]), ("適用坪數", ["8坪", "12坪", "18坪", "24坪"])],
    "空氣清淨機": [("適用坪數", ["6坪", "12坪", "20坪"]), ("濾網", ["HEPA H13", "HEPA H11", "活性碳複合"])],
    "電風扇": [("尺寸", ["14吋", "16吋", "DC 風扇"]), ("控制", ["機械式", "遙控"])],
    "電鍋": [("容量", ["6人份", "10人份", "11人份"]), ("材質", ["不鏽鋼內鍋", "陶瓷內鍋"])],
    "掃地機器人": [("功能", ["純掃地", "掃拖二合一", "自動集塵"]), ("續航", ["90分鐘", "150分鐘"])],
    "吸塵器": [("型式", ["手持無線", "直立式", "臥式"]), ("吸力", ["120AW", "180AW"])],
    "紙尿褲": [("尺寸", ["S", "M", "L", "XL"]), ("包裝", ["單包", "箱購 4 包"])],
    "貓砂": [("材質", ["礦砂", "豆腐砂", "水晶砂"]), ("重量", ["5L", "10L", "20L"])],
    "行動電源": [("容量", ["10000mAh", "20000mAh"]), ("輸出", ["PD 20W", "PD 45W"])],
    "藍牙耳機": [("型式", ["真無線", "頸掛式"]), ("降噪", ["主動降噪", "無降噪"])],
}
DEFAULT_SPECS = [("規格", ["標準", "加大", "補充包"]), ("包裝", ["單入", "三入組", "箱購"])]

CATEGORY_PRICE_BANDS = {
    "家電": (990, 18900),
    "生活用品": (49, 599),
    "食品飲料": (69, 1290),
    "母嬰": (159, 2490),
    "寵物": (129, 2890),
    "3C周邊": (199, 4990),
    "居家修繕": (39, 1890),
    "運動戶外": (149, 2290),
}
ITEM_PRICE_BANDS = {
    "除濕機": (4500, 16000), "空氣清淨機": (2500, 15000), "電風扇": (690, 3990),
    "電鍋": (1200, 4500), "掃地機器人": (3990, 25000), "吸塵器": (1500, 16000),
    "洗衣精": (99, 399), "衛生紙": (180, 599), "垃圾袋": (49, 199),
    "收納箱": (129, 899), "除臭劑": (59, 249),
    "咖啡豆": (250, 990), "麥片": (99, 399), "調理包": (59, 299),
    "礦泉水": (99, 459), "堅果": (159, 699),
    "紙尿褲": (249, 1290), "濕紙巾": (39, 259), "奶瓶": (199, 899), "副食品調理機": (1290, 4990),
    "貓砂": (159, 899), "狗飼料": (299, 2890), "寵物零食": (59, 399), "自動餵食器": (890, 3990),
    "行動電源": (390, 1990), "USB-C 傳輸線": (99, 599), "藍牙耳機": (590, 6990),
    "機械鍵盤": (890, 4990), "螢幕支架": (490, 2990),
    "矽利康": (59, 299), "水管接頭": (39, 299), "LED 燈泡": (69, 499),
    "工具組": (299, 2490), "門把": (199, 1490),
    "瑜珈墊": (299, 1890), "登山水壺": (199, 1290), "護膝": (149, 899), "跳繩": (99, 599),
}

PROMOTIONS = [
    None,
    None,
    {"code": "bundle_2", "label": "第二件 8 折", "discount_rate": 0.2, "applies_from_quantity": 2},
    {"code": "member_5pct", "label": "會員 95 折", "discount_rate": 0.05, "applies_from_quantity": 1},
    {"code": "clearance", "label": "出清 7 折", "discount_rate": 0.3, "applies_from_quantity": 1},
    {"code": "free_shipping", "label": "本檔免運", "discount_rate": 0.0, "applies_from_quantity": 1},
]


def build() -> None:
    suppliers = [p for p in read_mock("master/providers.json") if p["service_type"] == "product_purchase"]
    random_source = rng("products")
    products: list[dict] = []
    inventory: list[dict] = []

    flat_items = [
        (category, item)
        for category, items in vocab.PRODUCT_CATEGORIES.items()
        for item in items
    ]

    index = 0
    while len(products) < TARGET_SKU_COUNT:
        category, item = flat_items[index % len(flat_items)]
        supplier = suppliers[index % len(suppliers)]
        brand = vocab.PRODUCT_BRANDS[(index * 7) % len(vocab.PRODUCT_BRANDS)]
        specs = SPEC_TEMPLATES.get(item, DEFAULT_SPECS)
        spec_values = {name: options[index % len(options)] for name, options in specs}

        sku = f"SKU-{100000 + index}"
        base_price = _price_for(category, item, random_source)
        stock = random_source.choice([0, 0, 3, 12, 30, 88, 250, 999])
        delivery = random_source.choice(vocab.DELIVERY_METHODS)
        # 大型家電只能走專車；食品不可退
        if category == "家電" and item in ("除濕機", "掃地機器人", "吸塵器"):
            delivery = vocab.DELIVERY_METHODS[3]
        return_policy = (
            vocab.RETURN_POLICIES[2]
            if category == "食品飲料"
            else vocab.RETURN_POLICIES[3]
            if category == "家電"
            else random_source.choice(vocab.RETURN_POLICIES[:2])
        )

        products.append(
            {
                "sku": sku,
                "product_id": stable_uuid("product", index),
                "supplier_id": supplier["provider_id"],
                "supplier_name": supplier["name"],
                "category": category,
                "name": f"{brand} {item} {' '.join(spec_values.values())}",
                "brand": brand,
                "item_type": item,
                "specs": spec_values,
                "unit": "件",
                "list_price": base_price,
                "sale_price": base_price,
                "currency": "TWD",
                "promotion": random_source.choice(PROMOTIONS),
                "delivery": {
                    **{k: v for k, v in delivery.items() if k != "days"},
                    "estimated_days": delivery["days"],
                    "cold_chain": category == "食品飲料" and item == "調理包",
                },
                "return_policy": return_policy,
                "warranty_months": 12 if category == "家電" else 0,
                "rating": round(random_source.uniform(3.4, 4.9), 1),
                "source": "synthetic",
            }
        )
        inventory.append(
            {
                "sku": sku,
                "supplier_id": supplier["provider_id"],
                "stock_on_hand": stock,
                "reserved": min(stock, random_source.randint(0, 5)),
                "restock_eta": None if stock > 0 else iso(D_DAY + timedelta(days=random_source.randint(3, 21))),
                "updated_at": iso(D_DAY),
            }
        )
        index += 1

    # 促銷價套用
    for product in products:
        promotion = product["promotion"]
        if promotion and promotion["discount_rate"] > 0 and promotion["applies_from_quantity"] == 1:
            product["sale_price"] = round(product["list_price"] * (1 - promotion["discount_rate"]))

    report(write_json("master/products.json", products), len(products))
    report(write_json("master/product_inventory.json", inventory), len(inventory))


def _price_for(category: str, item: str, random_source) -> int:
    """單價依「品項」而非「品類」取樣，避免濕紙巾賣到兩千的荒謬價格。"""
    low, high = ITEM_PRICE_BANDS.get(item, CATEGORY_PRICE_BANDS[category])
    return int(round(random_source.uniform(low, high) / 10) * 10)


if __name__ == "__main__":
    build()
