"""AstrBot Plugin: HowToCook (程序员做饭指南)
Based on Anduin2017/HowToCook with 370+ precision engineered recipes and kitchen tips.
Supports command direct access, natural language intent recognition, LLM Agent Tool Calling,
dynamic serving scaling, reverse ingredient matching, third-party link import, and clean poster card generation.
"""

from __future__ import annotations

import asyncio
import inspect
import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, MessageChain, filter
from astrbot.api.star import Context, Star, StarTools
from astrbot.core.message.components import Image, Plain

from .core.calculator import scale_calculation
from .core.db import RecipeDB
from .core.extractor import extract_urls, fetch_web_content, structure_recipe_with_llm
from .core.poster import render_recipe_card

PLUGIN_NAME = "astrbot_plugin_howtocook"


class HowToCook(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config
        self.db = RecipeDB()
        self._data_dir: Path = StarTools.get_data_dir(PLUGIN_NAME)
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._cache_dir: Path = self._data_dir / "cache"
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        self._pref_file = self._data_dir / "preferences.json"
        self._user_prefs: Dict[str, str] = self._load_prefs()
        logger.info(
            f"HowToCook 程序员做饭指南已加载！共索引 {len(self.db.recipes)} 道精细菜谱"
            f"（官方基线: {len(self.db.official_recipes)}，自建收录: {len(self.db.custom_recipes)}）与 {len(self.db.tips)} 篇下厨技巧。"
        )

    def _load_prefs(self) -> Dict[str, str]:
        if self._pref_file.exists():
            try:
                with open(self._pref_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return {}
        return {}

    def _save_prefs(self):
        try:
            with open(self._pref_file, "w", encoding="utf-8") as f:
                json.dump(self._user_prefs, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.warning(f"HowToCook: 保存偏好设置失败: {e}")

    def _origin(self, event: AstrMessageEvent) -> str:
        return str(event.unified_msg_origin)

    def _get_output_format(self, event: AstrMessageEvent) -> str:
        origin = self._origin(event)
        if origin in self._user_prefs:
            return self._user_prefs[origin]
        return str(self.config.get("output_format", "card")).strip().lower()

    def _parse_dish_request(self, raw_args: str) -> Tuple[str, int]:
        """Extracts dish name and servings from input like '可乐鸡翅 4人份'."""
        text = raw_args.strip()
        servings = 0
        m = re.search(r'(\d+)\s*(?:人份|份|人|个人)', text)
        if m:
            servings = int(m.group(1))
            text = text[:m.start()] + text[m.end():]
        dish_name = text.strip()
        return dish_name, servings

    def _format_text_recipe(self, recipe: Dict[str, Any], target_servings: int) -> str:
        """Formats recipe as a structured markdown message."""
        base_servings = recipe.get("base_servings", 2)
        servings_to_use = target_servings if target_servings > 0 else base_servings
        scaled_calc = scale_calculation(
            recipe.get("calculation", ""),
            base_servings=base_servings,
            target_servings=servings_to_use
        )

        stars = "★" * recipe.get("difficulty", 2) + "☆" * (5 - recipe.get("difficulty", 2))
        cal = recipe.get("calories")
        cal_str = f"{cal} 大卡" if cal else "暂未标注"
        tag_str = "【⭐ 私房自建】" if recipe.get("is_custom") else "【官方标准】"

        lines = [
            f"🍳 **{tag_str}【{recipe['name']}】做法指南**",
            f"🏷️ 分类：{recipe.get('category_name', '家常菜')} | 难度：{stars} | 卡路里：{cal_str}",
        ]
        if recipe.get("description"):
            lines.append(f"📝 简介：{recipe['description']}")

        lines.append("\n📋 **必备原料与用量：**")
        lines.append(scaled_calc if scaled_calc else "\n".join([f"* {i}" for i in recipe.get("ingredients", [])]))

        lines.append("\n🔥 **操作步骤：**")
        lines.append(recipe.get("operation", "暂无详细步骤"))

        if recipe.get("additional"):
            lines.append("\n💡 **小贴士与安全须知：**")
            lines.append(recipe["additional"])

        source = recipe.get("source_url")
        if source:
            lines.append(f"\n🔗 *收录自: {source}*")
        else:
            lines.append("\n📖 *来源：HowToCook 程序员做饭指南*")
        return "\n".join(lines)

    async def _send_image_result(self, event: AstrMessageEvent, image_path: str) -> bool:
        send = getattr(event, "send", None)
        if callable(send):
            try:
                ret = send(event.image_result(image_path))
                if inspect.isawaitable(ret):
                    await ret
                return True
            except Exception as e:
                logger.warning(f"howtocook: event.send 失败: {e}")
        try:
            origin = self._origin(event)
            await self.context.send_message(origin, MessageChain().file_image(image_path))
            return True
        except Exception as e:
            logger.warning(f"howtocook: context.send_message 失败: {e}")
            return False

    async def _deliver_recipe(self, event: AstrMessageEvent, recipe: Dict[str, Any], servings: int):
        fmt = self._get_output_format(event)
        base_servings = recipe.get("base_servings", 2)
        servings_to_use = servings if servings > 0 else base_servings

        if fmt == "card":
            try:
                scaled_calc = scale_calculation(
                    recipe.get("calculation", ""),
                    base_servings=base_servings,
                    target_servings=servings_to_use
                )
                custom_font = self.config.get("custom_font_path", "").strip() or None
                img_path = render_recipe_card(recipe, scaled_calc, self._cache_dir, custom_font=custom_font)
                yield event.image_result(img_path)
                return
            except Exception as e:
                logger.warning(f"howtocook: 绘制菜谱海报卡片异常，回退纯文本: {e}")

        # Text fallback or text mode
        yield event.plain_result(self._format_text_recipe(recipe, servings_to_use))

    # ==========================================
    # Commands
    # ==========================================

    @filter.command("做菜", alias={"菜谱", "howtocook", "做饭"})
    async def cmd_cook(self, event: AstrMessageEvent):
        """精准查阅菜谱及做法。用法：/做菜 <菜名> [人数/份数]"""
        raw = str(event.message_str or "").strip()
        parts = raw.split(maxsplit=1)
        args = parts[1].strip() if len(parts) > 1 else ""

        if not args:
            yield event.plain_result("👨‍🍳 请输入要查询的菜名，例如：\n/做菜 可乐鸡翅\n/做菜 拔丝土豆 4人份\n/吃什么 (随机抽签)")
            return

        dish_name, servings = self._parse_dish_request(args)
        recipe = self.db.get_recipe(dish_name)
        if not recipe:
            candidates = self.db.search_recipes(dish_name, limit=5)
            if candidates:
                cand_list = "\n".join([f"• /做菜 {c['name']}" for c in candidates])
                yield event.plain_result(f"抱歉，未找到名为「{dish_name}」的菜谱，您是否想看：\n{cand_list}")
            else:
                yield event.plain_result(f"抱歉，菜谱库中暂未收录「{dish_name}」。您可以使用 /吃什么 随机查看，或使用 /存菜谱 导入第三方菜谱。")
            return

        # Deliver recipe
        async for res in self._deliver_recipe(event, recipe, servings):
            yield res

        # Check if there are other variants of this dish
        variants = self.db.get_variants(dish_name)
        other_variants = [v for v in variants if v['name'] != recipe['name']]
        if other_variants:
            v_list = ", ".join([f"「{v['name']}」" for v in other_variants])
            yield event.plain_result(f"💡 发现该菜品还有其他自建版本：{v_list}，发送对应菜名即可查看不同做法！")

    @filter.command("吃什么", alias={"随机菜谱", "今天吃什么", "吃啥", "推荐菜谱"})
    async def cmd_what_to_eat(self, event: AstrMessageEvent):
        """随机推荐一道菜解决纠结。用法：/吃什么 [荤菜/素菜/水产/主食/难度]"""
        raw = str(event.message_str or "").strip()
        parts = raw.split(maxsplit=1)
        args = parts[1].strip() if len(parts) > 1 else ""

        category = None
        max_diff = None

        if args:
            for cat_token in ["素菜", "青菜", "荤菜", "肉", "水产", "海鲜", "主食", "早餐", "汤", "甜品", "半成品"]:
                if cat_token in args:
                    category = cat_token
                    break
            diff_m = re.search(r'(\d+)\s*(?:星|难度)', args)
            if diff_m:
                max_diff = int(diff_m.group(1))

        dish = self.db.random_dish(category=category, max_difficulty=max_diff)
        if not dish:
            yield event.plain_result("未找到符合筛选条件的推荐菜品，换个条件试试吧！")
            return

        stars = "★" * dish.get("difficulty", 2) + "☆" * (5 - dish.get("difficulty", 2))
        cal = dish.get("calories")
        cal_str = f" | 🔥 {cal} 大卡" if cal else ""
        custom_tag = "【⭐ 私房自建】" if dish.get("is_custom") else ""

        msg = (
            f"🎲 **今天为您推荐：{custom_tag}【{dish['name']}】**\n"
            f"🏷️ 分类：{dish.get('category_name', '家常菜')} | 难度：{stars}{cal_str}\n"
            f"📝 简介：{dish.get('description') or '美味可口的家庭料理'}\n\n"
            f"👉 发送 `/做菜 {dish['name']}` 查看完整图文步骤与克数用量！"
        )
        yield event.plain_result(msg)

    @filter.command("冰箱", alias={"查食材", "食材做菜", "做啥菜"})
    async def cmd_fridge(self, event: AstrMessageEvent):
        """冰箱食材反向配菜。用法：/冰箱 <食材1> [食材2] [食材3]..."""
        raw = str(event.message_str or "").strip()
        parts = raw.split(maxsplit=1)
        args = parts[1].strip() if len(parts) > 1 else ""

        if not args:
            yield event.plain_result("🧊 请输入您手头现有的食材，用空格分隔，例如：\n/冰箱 土豆 牛肉 番茄\n/冰箱 鸡蛋 西红柿")
            return

        user_ings = re.split(r'[,，、\s]+', args)
        matches = self.db.match_by_ingredients(user_ings, limit=int(self.config.get("max_recommendations", 5)))

        if not matches:
            yield event.plain_result(f"未能根据食材「{', '.join(user_ings)}」匹配到合适菜谱，请尝试提供更多食材或主料！")
            return

        lines = [f"🍳 **根据现有食材「{', '.join(user_ings)}」，为您推荐以下菜品：**\n"]
        for idx, item in enumerate(matches, 1):
            r = item["recipe"]
            matched = ", ".join(item["matched_main"]) or "常见常备调料"
            missing = ", ".join(item["missing_main"]) or "无需补充其他主料！"
            stars = "★" * r.get("difficulty", 2)
            custom_tag = " [自建]" if r.get("is_custom") else ""
            lines.append(
                f"**{idx}. 【{r['name']}】{custom_tag}** ({r.get('category_name')} · 难度 {stars})\n"
                f"  ✅ 命中主料：{matched}\n"
                f"  ⚠️ 仍需补充：{missing}\n"
                f"  👉 输入 `/做菜 {r['name']}` 即可开做\n"
            )

        yield event.plain_result("\n".join(lines))

    @filter.command("厨房技巧", alias={"下厨技巧", "做菜技巧", "烹饪技巧"})
    async def cmd_tips(self, event: AstrMessageEvent):
        """下厨基础操作技巧指南。用法：/厨房技巧 [关键词]"""
        raw = str(event.message_str or "").strip()
        parts = raw.split(maxsplit=1)
        kw = parts[1].strip() if len(parts) > 1 else ""

        if not kw:
            tip_names = [f"• {t['name']}" for t in self.db.tips]
            yield event.plain_result(
                "📚 **HowToCook 烹饪技巧指南库：**\n" +
                "\n".join(tip_names) +
                "\n\n请输入具体技巧查询，例如：`/厨房技巧 焯水` 或 `/厨房技巧 去腥`"
            )
            return

        tip = self.db.get_tip(kw)
        if not tip:
            yield event.plain_result(f"未找到关于「{kw}」的技巧指南，可输入 `/厨房技巧` 查看完整列表。")
            return

        yield event.plain_result(f"📖 **【{tip['name']}】指南：**\n\n{tip['content']}")

    @filter.command("做菜模式", alias={"howtocook_mode"})
    async def cmd_mode(self, event: AstrMessageEvent):
        """切换菜谱输出形式。用法：/做菜模式 card（海报长图）或 /做菜模式 text（纯文本）"""
        raw = str(event.message_str or "").strip()
        parts = raw.split(maxsplit=1)
        mode = parts[1].strip().lower() if len(parts) > 1 else ""

        origin = self._origin(event)
        if mode in ("card", "image", "海报", "图片"):
            self._user_prefs[origin] = "card"
            self._save_prefs()
            yield event.plain_result("✅ 已将当前会话的菜谱输出模式切换为：【海报长图卡片】（极简美观、防刷屏）")
        elif mode in ("text", "txt", "文字", "文本"):
            self._user_prefs[origin] = "text"
            self._save_prefs()
            yield event.plain_result("✅ 已将当前会话的菜谱输出模式切换为：【纯文本排版】")
        else:
            cur = self._get_output_format(event)
            cur_desc = "海报长图卡片" if cur == "card" else "纯文本排版"
            yield event.plain_result(f"当前模式：【{cur_desc}】\n用法：\n/做菜模式 card  (切换为长图海报)\n/做菜模式 text  (切换为纯文本)")

    # ==========================================
    # Third-Party Recipe Ingestion & Management
    # ==========================================

    @filter.command("存菜谱", alias={"收录", "导入菜谱", "import_recipe"})
    async def cmd_import_recipe(self, event: AstrMessageEvent):
        """分享第三方链接并自动收录为量化菜谱。用法：/存菜谱 <URL> [自定义菜名] [--overwrite]"""
        raw = str(event.message_str or "").strip()
        parts = raw.split(maxsplit=1)
        args = parts[1].strip() if len(parts) > 1 else ""

        urls = extract_urls(args)
        if not urls:
            yield event.plain_result(
                "📥 请提供要收录的第三方菜谱链接，例如：\n"
                "/存菜谱 https://www.xiachufang.com/recipe/xxxx/\n"
                "/存菜谱 https://xhslink.com/xxxx 新奥尔良烤翅\n"
                "（支持小红书、下厨房、B站、公众号、美食博客等链接）"
            )
            return

        target_url = urls[0]
        # Clean custom name by removing the url and flags
        remaining = args.replace(target_url, "").replace("--overwrite", "").strip()
        custom_name = remaining if remaining else ""
        overwrite = "--overwrite" in args

        # L1 URL duplicate check
        existing_url_recipe = self.db.check_url_exists(target_url)
        if existing_url_recipe and not overwrite:
            yield event.plain_result(
                f"⚠️ 该链接已于 {existing_url_recipe.get('created_at', '之前')} 收录过！\n"
                f"菜品名称：【{existing_url_recipe['name']}】\n"
                f"👉 直接发送 `/做菜 {existing_url_recipe['name']}` 即可查看。\n"
                f"（若需重新抓取并更新，请添加 `--overwrite` 参数）"
            )
            return

        yield event.plain_result("🔍 正在抓取网页并由 AI 重构为【HowToCook】量化工程规范，请稍候约 5-10 秒...")

        try:
            # 1. Fetch web content
            title, raw_markdown = fetch_web_content(target_url)
            if not raw_markdown.strip():
                yield event.plain_result("❌ 抓取网页内容为空，请检查链接是否需要特殊登录验证。")
                return

            # 2. LLM structuring
            recipe_data = await structure_recipe_with_llm(
                self.context,
                raw_content=raw_markdown,
                source_url=target_url,
                custom_name=custom_name,
                umo=self._origin(event)
            )

            # 3. L2/L3 collision check & resolution
            col_type, existing_dish = self.db.check_collision(recipe_data["name"])
            saved_recipe, status_msg = self.db.save_custom_recipe(
                recipe_data,
                overwrite=overwrite,
                resolve_mode="overwrite" if overwrite else "variant"
            )

            # 4. Confirmation message
            notice = (
                f"🎉 **菜谱收录成功！【{saved_recipe['name']}】**\n"
                f"📌 状态：{status_msg}\n"
                f"🏷️ 分类：{saved_recipe.get('category_name')} | 难度：{'★' * saved_recipe.get('difficulty', 2)} | 预估：{saved_recipe.get('calories')} 大卡\n"
                f"📝 简介：{saved_recipe.get('description')}\n"
                f"🔗 来源：{target_url}\n\n"
                f"👇 已为您同步生成规范菜谱海报长图："
            )
            yield event.plain_result(notice)

            # Deliver card
            async for res in self._deliver_recipe(event, saved_recipe, servings=saved_recipe.get("base_servings", 2)):
                yield res

        except Exception as e:
            logger.error(f"HowToCook: 收录菜谱异常: {e}", exc_info=True)
            yield event.plain_result(f"❌ 收录菜谱失败：{e}。请检查链接或稍后重试。")

    @filter.command("我的菜谱", alias={"自建菜谱", "收录列表"})
    async def cmd_my_recipes(self, event: AstrMessageEvent):
        """查看您已收录的自建/第三方菜谱。用法：/我的菜谱"""
        customs = self.db.list_custom_recipes()
        if not customs:
            yield event.plain_result(
                "📂 您的私房自建菜谱库目前为空。\n"
                "遇到好吃的菜谱，只需发送 `/存菜谱 <链接>` 即可一键收录为量化标准菜谱！"
            )
            return

        lines = [f"📖 **我的私房收录菜谱库（共 {len(customs)} 道）：**\n"]
        for idx, r in enumerate(customs, 1):
            stars = "★" * r.get("difficulty", 2)
            time_str = r.get("created_at", "未知")
            lines.append(
                f"**{idx}. 【{r['name']}】** ({r.get('category_name', '家常菜')} · 难度 {stars})\n"
                f"   - 收录时间：{time_str}\n"
                f"   - 来源：{r.get('source_url', '自建')}\n"
                f"   - 查看指令：`/做菜 {r['name']}`\n"
            )

        lines.append("💡 发送 `/删除菜谱 <菜名>` 可移除不需要的收录。")
        yield event.plain_result("\n".join(lines))

    @filter.command("删除菜谱", alias={"del_recipe"})
    async def cmd_del_recipe(self, event: AstrMessageEvent):
        """删除已收录的私房菜谱。用法：/删除菜谱 <菜名>"""
        raw = str(event.message_str or "").strip()
        parts = raw.split(maxsplit=1)
        name = parts[1].strip() if len(parts) > 1 else ""

        if not name:
            yield event.plain_result("请输入要删除的自建菜名，例如：`/删除菜谱 新奥尔良烤翅·空气炸锅版`")
            return

        # Protect official recipes
        col_type, _ = self.db.check_collision(name)
        if col_type == "OFFICIAL":
            yield event.plain_result("🛡️ 【官方标准菜谱】受系统写保护，不可删除。只能删除您的私房收录菜谱。")
            return

        ok = self.db.delete_custom_recipe(name)
        if ok:
            yield event.plain_result(f"✅ 已成功从您的私房库中删除菜谱【{name}】！")
        else:
            yield event.plain_result(f"未找到自建菜谱【{name}】，可发送 `/我的菜谱` 查看现有收录列表。")

    # ==========================================
    # Natural Language Direct Regex Triggers
    # ==========================================

    @filter.regex(r'^(想吃|怎么做|教我做|做道|做个)\s*([^\s0-9]+)\s*(\d+人份)?$')
    async def regex_cook(self, event: AstrMessageEvent):
        match = re.match(r'^(想吃|怎么做|教我做|做道|做个)\s*([^\s0-9]+)\s*(\d+人份)?$', str(event.message_str).strip())
        if not match:
            return
        dish_name = match.group(2).strip()
        servings_str = match.group(3)
        servings = 0
        if servings_str:
            m = re.search(r'\d+', servings_str)
            if m:
                servings = int(m.group(0))

        recipe = self.db.get_recipe(dish_name)
        if recipe:
            async for res in self._deliver_recipe(event, recipe, servings):
                yield res

    @filter.regex(r'^(今天吃什么|今天吃啥|晚上吃啥|中午吃啥|吃什么好|推荐个菜)\s*(.*)$')
    async def regex_random(self, event: AstrMessageEvent):
        await self.cmd_what_to_eat(event)

    # Link sharing trigger: When user shares URL and asks to save / cook
    @filter.regex(r'(?:存一下|收录|记下|导入|学一下|保存|存菜谱|这个菜谱|怎么做)\s*(https?://[^\s]+)')
    async def regex_save_link(self, event: AstrMessageEvent):
        await self.cmd_import_recipe(event)

    # ==========================================
    # LLM Agent Tools (Function Calling)
    # ==========================================

    @filter.llm_tool(name="howtocook_get_recipe")
    async def tool_get_recipe(
        self,
        event: AstrMessageEvent,
        dish_name: str,
        servings: int = 0,
        send_card_image: bool = True
    ) -> str:
        """获取指定菜谱的详尽做法，包含必备原料、克数换算及分步骤操作规范。
        当用户的诉求表达了询问某个具体菜品的做法、食材配比、制作步骤时，中枢智能网关应调用此工具。

        Args:
            dish_name(string): 菜品名称（如 "可乐鸡翅"、"拔丝土豆"、"罗宋汤"）。
            servings(number): 期望就餐人数/份数（例如 4 人份）。默认为 0（使用菜谱原方标准基准份数）。
            send_card_image(boolean): 是否自动向聊天窗口发送高清菜谱长图海报（推荐为 true）。
        """
        recipe = self.db.get_recipe(dish_name)
        if not recipe:
            candidates = self.db.search_recipes(dish_name, limit=3)
            if candidates:
                cand_str = ", ".join([c["name"] for c in candidates])
                return f"未找到名为「{dish_name}」的菜谱，但找到了相似菜品：{cand_str}。请询问用户是否要查询其中之一。"
            return f"菜谱库中暂未收录「{dish_name}」。建议向用户提供类似菜品的通用烹饪建议，或提醒用户可以通过发送第三方菜谱链接使用 /存菜谱 进行收录。"

        base_servings = recipe.get("base_servings", 2)
        servings_to_use = servings if servings > 0 else base_servings
        scaled_calc = scale_calculation(
            recipe.get("calculation", ""),
            base_servings=base_servings,
            target_servings=servings_to_use
        )

        image_sent = False
        if send_card_image:
            try:
                custom_font = self.config.get("custom_font_path", "").strip() or None
                img_path = render_recipe_card(recipe, scaled_calc, self._cache_dir, custom_font=custom_font)
                image_sent = await self._send_image_result(event, img_path)
            except Exception as e:
                logger.warning(f"howtocook: tool 发送海报失败: {e}")

        text_summary = self._format_text_recipe(recipe, servings_to_use)
        status_note = "【系统提示：高清菜谱长图已直接发送至用户聊天界面】\n" if image_sent else ""
        return f"{status_note}以下为【{recipe['name']}】的完整烹饪数据：\n\n{text_summary}"

    @filter.llm_tool(name="howtocook_recommend_by_ingredients")
    async def tool_recommend_by_ingredients(
        self,
        event: AstrMessageEvent,
        ingredients: List[str],
        limit: int = 5
    ) -> str:
        """根据用户手头现有的食材列表进行反向智能配菜（冰箱查菜）。
        分析计算最匹配的菜谱，并指出命中主料与缺失需补充的主料。

        Args:
            ingredients(list[string]): 用户现有的食材名称列表（例如 ["土豆", "牛肉", "番茄"]）。
            limit(number): 最多推荐的菜品数量，默认 5。
        """
        if not ingredients:
            return "请提供至少一种现有食材。"

        matches = self.db.match_by_ingredients(ingredients, limit=limit)
        if not matches:
            return f"未能根据食材「{', '.join(ingredients)}」在菜谱库中匹配到合适菜肴。"

        out = [f"根据现有食材 {ingredients}，推荐以下菜品：\n"]
        for idx, m in enumerate(matches, 1):
            r = m["recipe"]
            out.append(
                f"{idx}. 【{r['name']}】（分类：{r.get('category_name')}，难度：{r.get('difficulty')}星）\n"
                f"   - 命中主料：{', '.join(m['matched_main']) or '常用调料'}\n"
                f"   - 缺失需补充主料：{', '.join(m['missing_main']) or '无！现有材料已齐全'}\n"
                f"   - 主料覆盖率：{m['main_coverage']}%\n"
            )
        out.append("请结合上述结果以亲切热情的口吻向用户推荐，并提醒他们缺少哪些食材。")
        return "\n".join(out)

    @filter.llm_tool(name="howtocook_random_dish")
    async def tool_random_dish(
        self,
        event: AstrMessageEvent,
        category: str = "",
        max_difficulty: int = 0
    ) -> str:
        """当用户没有主见、纠结“今天吃什么/推荐个菜”时，随机挑选一道菜品。

        Args:
            category(string): 菜品分类偏好，可选：荤菜、素菜、水产、早餐、主食、汤与粥、甜品、半成品。留空表示不限。
            max_difficulty(number): 最大难度星级限制（1到5星，如 2 代表只需简单快手菜）。0 表示不限。
        """
        dish = self.db.random_dish(category=category, max_difficulty=max_difficulty if max_difficulty > 0 else None)
        if not dish:
            return "未能找到符合该条件的菜品，请尝试放宽分类或难度限制。"

        return (
            f"为您随机推荐了菜品：【{dish['name']}】\n"
            f"分类：{dish.get('category_name')}，难度：{dish.get('difficulty')}星，卡路里：{dish.get('calories') or '未知'}\n"
            f"简介：{dish.get('description')}\n"
            f"如果用户满意，可以继续调用 howtocook_get_recipe 获取详细操作步骤或直接向用户介绍。"
        )

    @filter.llm_tool(name="howtocook_get_tips")
    async def tool_get_tips(
        self,
        event: AstrMessageEvent,
        keyword: str
    ) -> str:
        """检索厨房与烹饪基础技巧（如：焯水、去腥、用刀、微波炉、高压力锅、食品安全、油温判断、如何洗碗等）。

        Args:
            keyword(string): 烹饪技巧关键词（如 "焯水"、"去腥"、"油温"、"高压锅"）。
        """
        tip = self.db.get_tip(keyword)
        if not tip:
            all_tips = ", ".join([t["name"] for t in self.db.tips])
            return f"未找到关于「{keyword}」的技巧指南。现有技巧库包含：{all_tips}。"

        return f"【{tip['name']}】的权威规范指南如下：\n\n{tip['content']}"

    @filter.llm_tool(name="howtocook_import_recipe_from_url")
    async def tool_import_recipe_from_url(
        self,
        event: AstrMessageEvent,
        url: str,
        custom_name: str = "",
        overwrite: bool = False
    ) -> str:
        """当用户分享第三方平台（小红书、下厨房、B站、公众号、博客等）的菜谱链接并希望保存、收录到菜谱库时调用此工具。
        此工具会自动抓取网页、由大模型重构为 HowToCook 规范并存入自建库，并立即发送长图海报。

        Args:
            url(string): 第三方菜谱的有效 HTTP/HTTPS 链接。
            custom_name(string): 用户指定的自定义菜名（可选，留空则自动提取）。
            overwrite(boolean): 若存在同名自建菜谱时是否覆盖（默认 false，保存为变体版）。
        """
        try:
            # Check L1 URL duplicate
            existing = self.db.check_url_exists(url)
            if existing and not overwrite:
                return (
                    f"该链接此前已收录过！菜名为【{existing['name']}】，已在库中。"
                    f"你可以直接向用户介绍这道菜，或询问是否需要发送海报长图。"
                )

            title, raw_markdown = fetch_web_content(url)
            if not raw_markdown.strip():
                return "抓取第三方网页内容失败，未能提取到有效正文。"

            recipe_data = await structure_recipe_with_llm(
                self.context,
                raw_content=raw_markdown,
                source_url=url,
                custom_name=custom_name,
                umo=self._origin(event)
            )

            saved, msg = self.db.save_custom_recipe(
                recipe_data,
                overwrite=overwrite,
                resolve_mode="overwrite" if overwrite else "variant"
            )

            # Render card and send directly
            scaled_calc = scale_calculation(
                saved.get("calculation", ""),
                base_servings=saved.get("base_servings", 2),
                target_servings=saved.get("base_servings", 2)
            )
            custom_font = self.config.get("custom_font_path", "").strip() or None
            img_path = render_recipe_card(saved, scaled_calc, self._cache_dir, custom_font=custom_font)
            await self._send_image_result(event, img_path)

            return (
                f"【成功收录并入库】菜名：【{saved['name']}】（{msg}）！\n"
                f"分类：{saved.get('category_name')}，预估难度：{saved.get('difficulty')}星，卡路里：{saved.get('calories')}大卡。\n"
                f"高清菜谱长图海报已直接送达用户聊天界面！请以热情随和的口吻向用户汇报收录成功，并简要介绍该菜特色。"
            )
        except Exception as e:
            logger.error(f"howtocook_import_recipe_from_url 失败: {e}", exc_info=True)
            return f"收录失败：{e}。请向用户致歉并说明可能的原因。"
