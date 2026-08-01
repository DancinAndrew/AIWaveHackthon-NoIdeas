"""把結構化 skeleton 反向組成使用者口語句子。

組合式設計：每個欄位有多個講法片段，句子 = 開場 + 已知欄位片段 + 收尾。
只有 skeleton 標為 present 的欄位才會出現在句子裡，因此 ground truth
（該抽到什麼、缺什麼）天生正確，不需要人工標注。
"""

from __future__ import annotations

from typing import Callable

Fragment = Callable[[dict, "object"], str]

OPENERS = {
    "polite": ["你好，", "您好，想請問一下，", "不好意思打擾了，", "哈囉，想麻煩你們，"],
    "terse": ["", "", "幫我看一下 "],
    "rambling": [
        "唉這個真的很煩，拖很久了，",
        "我先講一下狀況喔，",
        "本來想說算了，但實在受不了，",
        "上次找人來看過但沒解決，",
    ],
    "voice_typo": ["呃 我想說", "那個 我要", "欸 幫我", "我想要說"],
}
CLOSERS = {
    "polite": ["謝謝！", "麻煩你了，謝謝。", "再麻煩幫我安排，感謝。", "請問可以嗎？"],
    "terse": ["", "", "報個價"],
    "rambling": ["拜託幫我處理一下，真的快瘋了。", "希望可以趕快解決，謝謝。", "不然我不知道要找誰了。"],
    "voice_typo": ["這樣可以嗎", "麻煩囉", "先這樣"],
}

# 語音轉文字常見同音錯字，用來製造非乾淨輸入
VOICE_TYPO_MAP = {
    "冷氣": "冷器",
    "漏水": "漏誰",
    "馬桶": "馬統",
    "訂位": "定位",
    "清潔": "清結",
    "熱水器": "熱水氣",
    "管委會": "管未會",
    "預算": "預散",
}


def _apply_voice_typos(text: str, random_source) -> str:
    for source, typo in VOICE_TYPO_MAP.items():
        if source in text and random_source.random() < 0.4:
            text = text.replace(source, typo, 1)
    return text


# ------------------------------------------------------------- 各類別欄位片段

RESTAURANT: dict[str, list[str]] = {
    "location": ["在{district}", "{county}{district}這邊", "{district}附近", "地點希望在{district}"],
    "reservation_at": ["{date_text}{time_text}", "想訂{date_text}{time_text}", "{date_text}{time_text}的位子"],
    "party_size": ["{party_size}個人", "我們{party_size}位", "大概{party_size}個大人"],
    "cuisine": ["想吃{cuisine}", "{cuisine}的餐廳", "找{cuisine}", "想找{cuisine}類型的"],
    "budget": ["一個人抓{budget}左右", "預算每人{budget}上下", "不要超過每人{budget}"],
    "dietary": ["有人吃{dietary}", "其中一位需要{dietary}", "要注意{dietary}"],
    "seating": ["希望有{seating}", "想要{seating}", "可以的話要{seating}"],
    "children": ["帶{children}個小孩", "有{children}個小朋友要兒童椅"],
    "occasion": ["幫家人慶生", "公司聚餐", "朋友聚會", "紀念日", "招待客戶"],
}

PRODUCT: dict[str, list[str]] = {
    "query": ["想買{item}", "要一台{item}", "在找{item}", "需要{item}"],
    "category": ["算是{category}類的", "{category}那個分類"],
    "budget": ["預算{budget}以內", "希望{budget}左右", "不要超過{budget}"],
    "quantity": ["要{quantity}個", "數量{quantity}", "買{quantity}件"],
    "brand": ["最好是{brand}", "指定{brand}", "{brand}的優先"],
    "spec": ["規格要{spec}", "希望是{spec}", "要{spec}那種"],
    "delivery": ["寄到{district}", "送{county}{district}", "收貨地在{district}"],
    "deadline": ["{deadline}前要到", "希望{deadline}以前收到", "最晚{deadline}"],
    # 前兩個 = 可接受替代品，第三個 = 不接受
    "substitute": ["沒有的話類似的也可以", "可以接受替代品", "一定要這款不要換"],
}

HOUSEKEEPING: dict[str, list[str]] = {
    "service_items": ["想預約{items}", "需要{items}", "要做{items}"],
    "property_type": ["我家是{property_type}", "{property_type}", "住{property_type}"],
    "area": ["大概{area}坪", "{area}坪左右", "室內{area}坪"],
    "rooms": ["{rooms}房", "{rooms}房{bathrooms}衛"],
    "location": ["在{county}{district}", "{district}這邊", "地址在{district}"],
    "time": ["希望{date_text}{time_text}", "{date_text}可以嗎", "想約{date_text}{time_text}"],
    "frequency": ["{frequency_text}", "希望{frequency_text}"],
    # 前兩個 = 有寵物，第三個 = 沒寵物；由 __pick__ 指定，不可亂選
    "pets": ["家裡有養貓狗", "有寵物要注意", "沒有養寵物"],
    "supplies": ["清潔用品你們帶", "我這邊有清潔用品", "希望用環保清潔劑"],
    "photos": ["照片我可以拍給你們看", "有拍幾張現場照片"],
}

REPAIR: dict[str, list[str]] = {
    "symptom": [
        "{symptom}",
        "狀況是{symptom}",
        "問題是{symptom}",
        "從{when_started}開始{symptom}",
    ],
    "issue_type": ["應該是{issue_label}的問題", "{issue_label}那邊", "跟{issue_label}有關"],
    "location": ["我住{county}{district}", "在{district}", "地址{district}"],
    "asset": ["{asset}是{brand}的", "設備是{brand}{asset}", "{asset}用了{age}年"],
    # index 對應 urgency：0 routine / 1 soon / 2 urgent / 3 emergency
    "urgency": [
        "不急，這週有空再說",
        "希望這兩三天內可以排到",
        "蠻急的，今天或明天可以來嗎",
        "非常急，已經沒辦法正常使用了",
    ],
    "hazard": {
        "electric_shock_risk": ["碰到會有電到的感覺", "摸開關會麻麻的"],
        "exposed_wires": ["電線都露出來了", "看得到裸線"],
        "smoke_or_burning_smell": ["有燒焦味", "剛剛有冒煙", "聞到塑膠燒掉的味道"],
        "active_flooding": ["水一直流停不下來", "地板已經淹了", "水漫出來了"],
        "gas_smell": ["有聞到瓦斯味", "廚房一直有瓦斯的味道"],
    },
    "time": ["{date_text}{time_text}我在家", "希望{date_text}來", "我{time_text}都可以"],
    "photos": ["照片我拍好了", "可以傳照片給師傅看"],
}

COMMUNITY: dict[str, list[str]] = {
    "community": ["我是{community}的住戶", "這裡是{community}", "{community}"],
    "issue": ["想反映{issue_label}的問題", "{issue_label}一直沒處理", "關於{issue_label}"],
    "description": ["{description}", "情況是{description}"],
    # index 對應 urgency：0 routine / 1 soon / 2 urgent / 3 emergency
    "urgency": [
        "不急，先跟你們登記一下",
        "希望這週內有人回覆",
        "蠻急的，希望盡快處理",
        "已經影響到住戶安全，需要馬上處理",
    ],
    "location": ["在{county}{district}", "{district}這邊"],
    "affected_area": ["位置在{affected_area}", "{affected_area}那邊"],
    "attachment": ["我有拍照存證", "有錄影可以提供"],
    # index 0/1 = 希望匿名，2 = 願意具名
    "anonymity": [
        "可以的話不要讓其他住戶知道是我反映的",
        "希望以匿名方式處理",
        "我不介意具名，可以直接聯絡我",
    ],
}

FRAGMENTS = {
    "restaurant_reservation": RESTAURANT,
    "product_purchase": PRODUCT,
    "housekeeping_service": HOUSEKEEPING,
    "utility_repair": REPAIR,
    "community_consultation": COMMUNITY,
}


def compose(service_type: str, present: dict[str, dict], style: str, random_source) -> str:
    """present: {fragment_key: {slot: value}}，只組合有給的欄位。"""
    bank = FRAGMENTS[service_type]
    parts: list[str] = []
    for key, slots in present.items():
        options = bank.get(key)
        if options is None:
            continue
        if isinstance(options, dict):
            # hazard 這種以子鍵區分的片段
            for sub_key, sub_options in options.items():
                if slots.get(sub_key):
                    parts.append(random_source.choice(sub_options))
            continue
        # __pick__ 指定講法索引：語意由欄位值決定的片段（有無寵物、急不急、
        # 是否接受替代品）不能亂選，否則句子會和 ground truth 互相矛盾。
        pick = slots.get("__pick__")
        template = options[pick % len(options)] if pick is not None else random_source.choice(options)
        parts.append(template.format(**{k: v for k, v in slots.items() if k != "__pick__"}))

    random_source.shuffle(parts)
    opener = random_source.choice(OPENERS[style])
    closer = random_source.choice(CLOSERS[style])
    separator = random_source.choice(["，", "，", "。", " "])
    body = separator.join(p for p in parts if p)
    text = f"{opener}{body}{'。' if body and not body.endswith(('。', '，', ' ')) else ''}{closer}"
    text = text.replace("，。", "。").replace("。。", "。").strip()
    if style == "voice_typo":
        text = _apply_voice_typos(text, random_source)
    return text
