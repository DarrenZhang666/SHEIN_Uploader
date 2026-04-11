# -*- coding: utf-8 -*-
"""
shein_sensitive_clean.py
商品文案 & 标题敏感词过滤模块

使用方式：
    from shein_sensitive_clean import SENSITIVE_WORDS, TITLE_SENSITIVE_WORDS, _filter_sensitive, _filter_title
"""

import re

# ── 商品文案敏感词集合（含任一词的整句将被过滤）──────────────────────
# 每个词不区分大小写，逐句匹配，命中则整句删除
SENSITIVE_WORDS = [
    # 促销 / 价格相关
    "sales", "on sale", "clearance", "fire sale", "blowout", "final sale",
    "flash sale", "must buy", "limited time only", "never again",
    "cheapest", "lowest price", "rock bottom price",
    # 免费 / 退款
    "free", "zero cost", "refund unconditionally", "for nothing",
    # 销量标榜
    "best seller", "top sales", "sales champion", "sold out", "hot sale",
    "bestselling", "number one in sales", "millions sold",
    # 平台 / 渠道专属
    "official subsidy", "platform exclusive", "only for SHEIN", "live exclusive",
    # 极限用词
    "best", "top", "no.1", "first", "only", "perfect", "ultimate", "extreme",
    "top-level", "world-class", "national", "global",
    "100%", "forever", "never", "unique", "incomparable",
    "champion", "leader", "unbeatable",
    # 环保 / 认证
    "eco-friendly", "carbon neutral", "biodegradable", "non-polluting",
    "OEKO-TEX certified", "CE certified", "FDA approved",
    # 材质 / 工艺
    "organic", "100% cotton", "pure gold", "pure silver",
    "handmade", "pure natural", "imported", "original",
    # 维权 / 保证
    "invalid refund", "fake one pay ten", "lifetime warranty",
    "never fade", "zero risk", "no allergy at all",
    # 医疗 / 功效宣称
    "medical", "therapeutic", "cure", "treat", "heal",
    "anti-inflammatory", "sterilizing", "detox",
    "weight loss", "slimming", "whitening", "anti-aging", "anti-wrinkle",
    "acne removal", "spot fading", "medical grade", "no side effects", "seguro", "FILA", "Safe","Sustainable",
    "Eco",'eco-conscious','environmentally friendly','green','sustainable fashion','recycled materials','organic cotton',
    'vegan leather','biodegradable packaging',"Environmentally","cotton","concept"
    # 在此处继续添加敏感词，每行一个，字符串格式
]


def _remove_brand_words(text):
    """删除文本中疑似品牌名的词：
    判断标准：单个词（以空白/标点分隔）全部由大写字母组成，且长度 >= 2。
    只删除该词本身，不删除整句。
    例："NIKE shoes for women" -> "shoes for women"
    """
    if not text:
        return text
    # 匹配前后为非字母数字边界、全大写、长度>=2的单词（允许连字符如 T-SHIRT 不处理，只处理纯大写）
    result = re.sub(r'(?<![\w])([A-Z]{2,})(?![\w])', '', text)
    # 合并多余空格
    result = re.sub(r'  +', ' ', result).strip()
    return result


def _filter_sensitive(text):
    """过滤文案中含敏感词的整句（以句号、感叹号、换行为分句依据）。
    同时删除各句中疑似品牌名的全大写词。
    """
    if not text or not SENSITIVE_WORDS:
        return _remove_brand_words(text) if text else text
    sentences = re.split(r'(?<=[.!?\n])', text)
    filtered = []
    for sent in sentences:
        lower = sent.lower()
        if any(w.lower() in lower for w in SENSITIVE_WORDS):
            continue
        filtered.append(_remove_brand_words(sent))
    return ''.join(filtered).strip()


# ── 标题敏感词集合（从 标题敏感词.txt 提取，整词/短语不区分大小写匹配，命中则删除该词）────
# 如需更新，请编辑同目录下的「标题敏感词.txt」文件，或直接在此列表增删
TITLE_SENSITIVE_WORDS = [
    "politics",
    "political",
    "religion",
    "religious",
    "church",
    "bible",
    "allah",
    "national",
    "national-level",
    "government",
    "official",
    "for country",
    "violence",
    "violent",
    "sexy",
    "sex",
    "porn",
    "nude",
    "kill",
    "gun",
    "weapon",
    "drug",
    "smoke",
    "alcohol",
    "counterfeit",
    "fake",
    "replica",
    "pirated",
    "discrimination",
    "racist",
    "slave",
    "forbidden",
    "prohibited",
    "sales",
    "after-sales service",
    "after-sale",
    "retail",
    "wholesale",
    "custom service",
    "customer service",
    "medical",
    "medicinal",
    "therapy",
    "treat",
    "cure",
    "heal",
    "anti-inflammatory",
    "antibacterial",
    "sterilization",
    "detox",
    "whitening",
    "anti-aging",
    "remove wrinkles",
    "acne removal",
    "fade spots",
    "weight loss",
    "slimming",
    "firming",
    "umbra"
    # 在此处继续添加标题敏感词
]


def _filter_title(title):
    """清洗商品标题：
    1. 删除含敏感词的整个词/短语（不区分大小写，词边界匹配）
    2. 删除疑似品牌名的全大写词（长度>=2，前后为非字母边界）
    3. 删除孤立单字母（前后均为空格/边界，如 "A  B" 中的 A 和 B）
    4. 合并多余空格，去除首尾空白
    """
    if not title:
        return title
    result = title
    # 按词长降序，先替换长词避免短词误伤
    for w in sorted(TITLE_SENSITIVE_WORDS, key=lambda x: len(x), reverse=True):
        pattern = re.compile(
            r'(?<![\w-])' + re.escape(w) + r'(?![\w-])',
            re.IGNORECASE)
        result = pattern.sub('', result)
    # 删除疑似品牌名（全大写词，长度>=2）
    result = _remove_brand_words(result)
    # 删除孤立单字母（前后为空格或字符串边界）
    result = re.sub(r'(?:(?<=\s)|(?<=^))([A-Za-z])(?=\s|$)', '', result)
    # 合并多余空格
    result = re.sub(r'  +', ' ', result).strip()
    return result
