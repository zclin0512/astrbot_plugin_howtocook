"""Third-party recipe extractor and LLM normalization engine for HowToCook plugin.
Fetches web content via Jina Reader and restructures into HowToCook quantitative schema.
"""

from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

from astrbot.api import logger

URL_PATTERN = re.compile(r'https?://[^\s<>"\')]+', re.IGNORECASE)

LLM_SYSTEM_PROMPT = """你是一个严谨的【HowToCook 程序员做饭指南】工程化菜谱重构专家。
你的任务是将第三方平台（小红书、下厨房、B站、美食博客等）随意、口语化的菜谱内容，重构为符合 HowToCook 开源标准的精准量化 JSON 数据。

重构铁律：
1. 消灭模糊词汇：原文中的“适量”、“少许”、“一勺”、“少许盐”、“适量生抽”必须结合烹饪常识换算为标准精确数值（克 g、毫升 ml、个、只）。
2. 规范章节：
   - main_ingredients：主料（如肉类、主要蔬菜、海鲜），不要写调料；
   - pantry_ingredients：常备调料（油、盐、生抽、料酒、糖、葱姜蒜等）；
   - calculation：必须严格以“按照 2 人份的标准用量：”起头，列出每样食材的精确克数/毫升数；
   - operation：必须使用数字有序编号（1. 2. 3.），每个步骤必须包含明确的时间（如“中小火慢煎 3-4 分钟”）或可观察的物理状态变化判定标准（如“直至筷子能轻松穿透土豆”）；
   - additional：给出防翻车核心注意点。
3. 难度评级：1到5星的整数（1=极简5分钟，2=简单家常，3=需掌握火候，4=步骤繁多，5=易失误大菜）。
4. 卡路里：根据主要食材预估总大卡数（整数）。
5. 分类 category 必须严格为以下枚举之一：
   vegetable_dish, meat_dish, aquatic, breakfast, staple, soup, drink, condiment, dessert, semi-finished
"""


def extract_urls(text: str) -> List[str]:
    """Extracts all valid HTTP/HTTPS URLs from message text."""
    if not text:
        return []
    matches = URL_PATTERN.findall(text)
    cleaned = []
    for u in matches:
        # Strip trailing punctuation often caught in Chinese text
        u = u.rstrip('。，！？,!?）)》”"')
        if u and u not in cleaned:
            cleaned.append(u)
    return cleaned


def fetch_web_content(url: str, timeout: int = 15) -> Tuple[str, str]:
    """Fetches clean markdown content of a webpage using Jina Reader API with fallback.

    Returns:
        (title, markdown_content)
    """
    # 1. Try Jina Reader
    jina_url = f"https://r.jina.ai/{url}"
    req = urllib.request.Request(
        jina_url,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "X-Timeout": str(timeout),
        }
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            content = resp.read().decode('utf-8', errors='ignore')
            title = ""
            title_m = re.search(r'^Title:\s*(.+)$', content, re.M)
            if title_m:
                title = title_m.group(1).strip()
            if content.strip():
                return title, content
    except Exception as e:
        logger.warning(f"HowToCook: Jina Reader 抓取失败 ({e})，尝试直接抓取: {url}")

    # 2. Fallback direct fetch
    direct_req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
    )
    try:
        with urllib.request.urlopen(direct_req, timeout=timeout) as resp:
            html = resp.read().decode('utf-8', errors='ignore')
            # Extract title
            title_m = re.search(r'<title>(.*?)</title>', html, re.I | re.S)
            title = title_m.group(1).strip() if title_m else ""
            # Strip tags for raw text
            text = re.sub(r'<script.*?</script>', '', html, flags=re.I | re.S)
            text = re.sub(r'<style.*?</style>', '', text, flags=re.I | re.S)
            text = re.sub(r'<[^>]+>', '\n', text)
            clean_lines = [line.strip() for line in text.splitlines() if line.strip()]
            return title, "\n".join(clean_lines[:300])
    except Exception as e:
        logger.error(f"HowToCook: 网页直接抓取失败: {e}")
        raise RuntimeError(f"无法获取该网页内容，请检查链接有效性或手动输入菜谱文本。")


async def structure_recipe_with_llm(
    context: Any,
    raw_content: str,
    source_url: str,
    custom_name: str = "",
    umo: Optional[str] = None
) -> Dict[str, Any]:
    """Uses LLM to transform raw extracted text into HowToCook schema."""
    user_prompt = f"""请将以下网页提取出的菜谱文本，重构为符合【HowToCook】规范的精美量化菜谱。

用户指定菜名（若有）：{custom_name or '无（由大模型从内容智能提取）'}
原文链接：{source_url}

=== 网页提取正文开始 ===
{raw_content[:4000]}
=== 网页提取正文结束 ===

请严格仅输出如下 JSON 数据，不要包含任何 markdown 代码块标记以外的多余解释：
{{
  "name": "菜品名称（简洁正规中文名，如 可乐鸡翅、酸辣土豆丝）",
  "variant_tag": "特色标签（如 空气炸锅版、懒人免油版、低卡版，若与经典做法无异可留空字符串）",
  "category": "分类代号（必须是 vegetable_dish, meat_dish, aquatic, breakfast, staple, soup, drink, condiment, dessert, semi-finished 之一）",
  "difficulty": 1到5的数字,
  "calories": 预估卡路里数值（整数）,
  "description": "30-100字简述菜品风味、口感特点与制作耗时",
  "main_ingredients": ["核心主料1", "核心主料2"],
  "pantry_ingredients": ["常备调料1", "常备调料2"],
  "base_servings": 2,
  "calculation": "按照 2 人份的标准用量：\\n* 食材1：XX g\\n* 食材2：XX ml",
  "operation": "1. 步骤一（写明火候与时长）\\n2. 步骤二",
  "additional": "关键操作要点与防翻车提示"
}}
"""

    llm_output = ""

    # Strategy 1: AstrBot context.llm_generate
    try:
        chat_provider_id = None
        if umo and hasattr(context, "get_current_chat_provider_id"):
            try:
                chat_provider_id = await context.get_current_chat_provider_id(umo)
            except Exception:
                pass

        if not chat_provider_id and hasattr(context, "provider_manager"):
            pm = getattr(context, "provider_manager", None)
            if pm and hasattr(pm, "providers"):
                for pid, p in pm.providers.items():
                    if getattr(p, "active", True):
                        chat_provider_id = pid
                        break

        if chat_provider_id and hasattr(context, "llm_generate"):
            resp = await context.llm_generate(
                chat_provider_id=chat_provider_id,
                prompt=user_prompt,
                system_prompt=LLM_SYSTEM_PROMPT,
                temperature=0.1,
            )
            if resp and getattr(resp, "completion_text", None):
                llm_output = str(resp.completion_text).strip()
    except Exception as e:
        logger.warning(f"HowToCook: context.llm_generate 调用异常: {e}，尝试本地直连备用调用...")

    # Strategy 2: Direct call to local LLM endpoint
    if not llm_output:
        import urllib.request
        api_base = "http://192.168.31.185:18317/v1"
        api_key = "sk-local-466ab4bad536944739b79c1680d8bbcc0ae9df42e736ca17ab8ed0fa0e87cf68"
        payload = {
            "model": "gemini-3.8-flash-high",
            "messages": [
                {"role": "system", "content": LLM_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt}
            ],
            "temperature": 0.1
        }
        req = urllib.request.Request(
            f"{api_base}/chat/completions",
            data=json.dumps(payload).encode('utf-8'),
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            }
        )
        with urllib.request.urlopen(req, timeout=45) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            llm_output = data['choices'][0]['message']['content'].strip()

    # Parse JSON from LLM output
    json_str = llm_output
    json_match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', llm_output)
    if json_match:
        json_str = json_match.group(1).strip()
    else:
        json_str = json_str.strip()

    recipe_data = json.loads(json_str)

    # Post-process & clean fields
    if custom_name:
        recipe_data["name"] = custom_name.strip()

    # Assemble full ingredients
    main_ings = recipe_data.get("main_ingredients", [])
    pantry_ings = recipe_data.get("pantry_ingredients", [])
    recipe_data["ingredients"] = list(dict.fromkeys(main_ings + pantry_ings))

    # Add source citation to additional
    add = recipe_data.get("additional", "").strip()
    source_tag = f"\n* 收录来源：{source_url}"
    if source_tag not in add:
        recipe_data["additional"] = f"{add}\n{source_tag}".strip()

    recipe_data["source_url"] = source_url
    recipe_data["is_custom"] = True
    return recipe_data
