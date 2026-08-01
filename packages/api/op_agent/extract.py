"""規則式槽位抽取（LLM 的安全網）。

為什麼需要這層？
    實測發現模型會「嘴上說記下來了，但沒真的呼叫 update_request」，
    導致服務單是空的、前端進度條全白，看起來像壞掉。
    Prompt 再怎麼寫都無法保證工具一定被呼叫。

所以在呼叫 LLM 之前，先用規則把「明顯的」資訊抽出來寫進服務單。
LLM 的 update_request 之後仍會補上規則抓不到的細節（例如口語描述的機齡），
兩者是疊加而非互斥。

原則：只抽有明確關鍵詞依據的東西。寧可漏抽，不要猜錯 ——
猜錯地址會把師傅派到別人家。
"""

from __future__ import annotations

from .domain import Address, AcRepairSlots, PreferredContactTime, UserProfile
from .geo import resolve_address
from .seed import SYMPTOM_TO_ITEMS

# 時段關鍵詞。順序有意義：先比對「都可以」這類明確的全時段說法，
# 否則「早上晚上都可以」會被誤判成只有上午。
_PERIOD_RULES: list[tuple[tuple[str, ...], PreferredContactTime]] = [
    (("都可以", "都行", "皆可", "隨時", "都方便", "沒差"), "3"),
    (("上午", "早上", "早點", "白天"), "1"),
    (("下午", "午後", "傍晚", "晚點"), "2"),
]

# 機型關鍵詞
_VARIANTS = ("分離式", "窗型", "吊隱式", "落地式", "壁掛式")


def extract_symptoms(text: str) -> list[str]:
    """從訊息裡找出症狀關鍵詞。用 SYMPTOM_TO_ITEMS 的 key 當字典，
    這樣症狀詞彙與報價引擎的對照表永遠同步，不會有一邊改了另一邊沒改。"""
    found: list[str] = []
    for keyword in SYMPTOM_TO_ITEMS:
        if keyword in text and keyword not in found:
            found.append(keyword)
    # 「不夠冷」也含「不冷」，只留較具體的那個
    if "不夠冷" in found and "不冷" in found:
        found.remove("不冷")
    return found


def extract_period(text: str) -> PreferredContactTime | None:
    for keywords, code in _PERIOD_RULES:
        if any(k in text for k in keywords):
            return code
    return None


def extract_variant(text: str) -> str | None:
    return next((v for v in _VARIANTS if v in text), None)


def extract_address(text: str, user: UserProfile) -> Address | None:
    """解析地址。

    兩種來源：
      1. 訊息裡直接寫了縣市 + 行政區（例：「台北市大安區復興南路一段100號」）
      2. 訊息提到會員已存地址的特徵詞（例：「爸媽家」對應板橋那筆的備註）

    刻意不做模糊猜測 —— 會員有多個地址而訊息沒指明時回 None，
    讓管家去問。派錯地址的代價太高。
    """
    compact = text.replace(" ", "")

    # 來源 2：比對會員既有地址的可辨識片段
    for addr in user.get("addresses", []):
        detail = (addr.get("detail") or "").replace(" ", "")
        # 「爸媽家」這類寫在 detail 括號裡的線索
        for token in ("爸媽家", "父母家", "老家", "公司"):
            if token in detail and token in compact:
                return addr
        district = addr.get("districtName", "")
        # 「板橋那邊」「大安區那台」
        if district and district.rstrip("區") in compact:
            return addr

    # 來源 1：訊息本身就是完整地址
    return resolve_address(free_text=text)


def extract_appliance_hint(text: str, user: UserProfile) -> tuple[str | None, str | None, int | None]:
    """從「主臥那台」這種說法對應到會員的家電，回傳 (brand, variant, ageYears)。"""
    from datetime import date

    compact = text.replace(" ", "")
    for ap in user.get("appliances", []):
        if ap.get("kind") != "AC":
            continue
        location = ap.get("location") or ""
        brand = ap.get("brand") or ""
        matched = (location and location in compact) or (brand and brand in compact)
        if not matched:
            continue
        year = ap.get("installedYear")
        age = date.today().year - year if isinstance(year, int) else None
        return ap.get("brand"), ap.get("variant"), age

    return None, None, None


def extract_slots(text: str, user: UserProfile) -> tuple[AcRepairSlots, Address | None, PreferredContactTime | None]:
    """一次抽完，回傳 (slots, address, period)。抽不到的欄位不會出現在 slots 裡。"""
    slots: AcRepairSlots = {}

    symptoms = extract_symptoms(text)
    if symptoms:
        slots["symptoms"] = symptoms

    brand, variant, age = extract_appliance_hint(text, user)
    if brand:
        slots["brand"] = brand
    # 訊息裡明講的機型優先於從家電檔推的
    explicit_variant = extract_variant(text)
    if explicit_variant:
        slots["variant"] = explicit_variant
    elif variant:
        slots["variant"] = variant
    if age is not None:
        slots["ageYears"] = age

    return slots, extract_address(text, user), extract_period(text)
