"""Poster and image card generator for HowToCook recipes.
Renders clean, elegant, readable culinary guide cards using Pillow.
"""

from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from PIL import Image, ImageDraw, ImageFont

# Font sources within Linux / Docker container
FONT_CANDIDATES = (
    '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc',
    '/usr/share/fonts/opentype/noto/NotoSerifCJK-Regular.ttc',
    '/usr/share/fonts/truetype/wqy/wqy-microhei.ttc',
    '/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc',
    '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
)
FONT_BOLD_CANDIDATES = (
    '/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc',
    '/usr/share/fonts/opentype/noto/NotoSerifCJK-Bold.ttc',
    '/usr/share/fonts/truetype/wqy/wqy-microhei.ttc',
    '/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc',
    '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',
)


def _get_font(size: int, bold: bool = False, custom_path: Optional[str] = None) -> ImageFont.FreeTypeFont:
    paths = ([custom_path] if custom_path else []) + list(FONT_BOLD_CANDIDATES if bold else FONT_CANDIDATES)
    for p in paths:
        if p and os.path.isfile(p):
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                continue
    # Fallback default
    return ImageFont.load_default()


def _wrap_text(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont, max_width: int) -> List[str]:
    """Wraps text into lines that fit within max_width."""
    lines = []
    for paragraph in text.splitlines():
        if not paragraph.strip():
            lines.append("")
            continue
        current_line = ""
        for char in paragraph:
            test_line = current_line + char
            bbox = draw.textbbox((0, 0), test_line, font=font)
            w = bbox[2] - bbox[0]
            if w <= max_width:
                current_line = test_line
            else:
                lines.append(current_line)
                current_line = char
        if current_line:
            lines.append(current_line)
    return lines


def render_recipe_card(
    recipe: Dict[str, Any],
    calculation_text: str,
    output_dir: Path,
    custom_font: Optional[str] = None
) -> str:
    """Renders a recipe card and returns the output image file path."""
    output_dir.mkdir(parents=True, exist_ok=True)
    dish_id = recipe.get('name', 'recipe')
    content_hash = hashlib.md5(f"{dish_id}_{calculation_text}".encode('utf-8')).hexdigest()[:10]
    output_file = output_dir / f"recipe_{dish_id}_{content_hash}.png"

    if output_file.exists():
        return str(output_file)

    # Palette
    BG_COLOR = (250, 248, 245)       # warm cream
    CARD_BG = (255, 255, 255)        # clean white
    PRIMARY_COLOR = (217, 83, 79)    # coral red
    TEXT_MAIN = (38, 42, 51)         # dark slate
    TEXT_MUTED = (120, 126, 140)     # gray
    BORDER_COLOR = (235, 230, 222)   # light border
    BADGE_BG = (244, 235, 230)       # soft peach
    BADGE_TEXT = (192, 57, 43)

    WIDTH = 960
    PADDING = 48
    INNER_WIDTH = WIDTH - PADDING * 2

    # Fonts
    title_font = _get_font(42, bold=True, custom_path=custom_font)
    subtitle_font = _get_font(22, bold=False, custom_path=custom_font)
    sec_font = _get_font(26, bold=True, custom_path=custom_font)
    body_font = _get_font(22, bold=False, custom_path=custom_font)
    body_bold = _get_font(22, bold=True, custom_path=custom_font)
    meta_font = _get_font(20, bold=False, custom_path=custom_font)
    footer_font = _get_font(18, bold=False, custom_path=custom_font)

    # Pre-calculate layout height
    # Use a dummy image to measure
    dummy_img = Image.new('RGB', (WIDTH, 100), BG_COLOR)
    draw = ImageDraw.Draw(dummy_img)

    y = PADDING + 30
    y += 60  # Title
    y += 45  # Meta badges
    y += 20

    # Intro description
    desc = recipe.get('description', '').strip()
    if desc:
        desc_lines = _wrap_text(draw, desc, subtitle_font, INNER_WIDTH)
        y += len(desc_lines) * 34 + 30

    # Ingredients & Calculation Section
    y += 50  # Section title
    calc_to_render = calculation_text or '\n'.join([f"• {i}" for i in recipe.get('ingredients', [])])
    calc_lines = _wrap_text(draw, calc_to_render, body_font, INNER_WIDTH)
    y += len(calc_lines) * 32 + 35

    # Steps Section
    y += 50
    op_text = recipe.get('operation', '').strip()
    op_lines = _wrap_text(draw, op_text, body_font, INNER_WIDTH)
    y += len(op_lines) * 34 + 35

    # Additional Section
    add_text = recipe.get('additional', '').strip()
    if add_text:
        y += 50
        add_lines = _wrap_text(draw, add_text, body_font, INNER_WIDTH)
        y += len(add_lines) * 32 + 35

    y += 70  # Footer

    TOTAL_HEIGHT = max(y, 1000)

    # Real canvas
    img = Image.new('RGB', (WIDTH, TOTAL_HEIGHT), BG_COLOR)
    draw = ImageDraw.Draw(img)

    # Card background panel with rounded border effect
    draw.rounded_rectangle(
        [(PADDING // 2, PADDING // 2), (WIDTH - PADDING // 2, TOTAL_HEIGHT - PADDING // 2)],
        radius=24,
        fill=CARD_BG,
        outline=BORDER_COLOR,
        width=2
    )

    cur_y = PADDING + 20

    # 1. Header: Dish Title
    title = f"{recipe.get('name', '菜谱')} 的做法"
    draw.text((PADDING, cur_y), title, fill=PRIMARY_COLOR, font=title_font)
    cur_y += 60

    # 2. Badges: Category | Difficulty | Calories | (Custom badge)
    stars = '★' * recipe.get('difficulty', 2) + '☆' * (5 - recipe.get('difficulty', 2))
    cat_text = f"分类: {recipe.get('category_name', '家常菜')}"
    diff_text = f"难度: {stars}"
    cal_text = f"预估卡路里: {recipe.get('calories') or '--'} 大卡"

    badge_items = [cat_text, diff_text, cal_text]
    if recipe.get('is_custom'):
        badge_items.insert(0, "⭐ 私房自建收录")
    badge_x = PADDING
    for badge in badge_items:
        bbox = draw.textbbox((0, 0), badge, font=meta_font)
        bw = bbox[2] - bbox[0] + 24
        draw.rounded_rectangle([(badge_x, cur_y), (badge_x + bw, cur_y + 36)], radius=10, fill=BADGE_BG)
        draw.text((badge_x + 12, cur_y + 7), badge, fill=BADGE_TEXT, font=meta_font)
        badge_x += bw + 14
    cur_y += 55

    # 3. Intro description
    if desc:
        for line in desc_lines:
            draw.text((PADDING, cur_y), line, fill=TEXT_MUTED, font=subtitle_font)
            cur_y += 34
        cur_y += 20

    # Divider
    draw.line([(PADDING, cur_y), (WIDTH - PADDING, cur_y)], fill=BORDER_COLOR, width=1)
    cur_y += 25

    # 4. Ingredients & Calculation
    draw.text((PADDING, cur_y), "必备原料与用量配比", fill=TEXT_MAIN, font=sec_font)
    cur_y += 44
    for line in calc_lines:
        font_to_use = body_bold if line.startswith('**') or '自适应换算' in line else body_font
        color_to_use = PRIMARY_COLOR if '自适应换算' in line else TEXT_MAIN
        draw.text((PADDING + 10, cur_y), line.replace('**', ''), fill=color_to_use, font=font_to_use)
        cur_y += 32
    cur_y += 25

    # Divider
    draw.line([(PADDING, cur_y), (WIDTH - PADDING, cur_y)], fill=BORDER_COLOR, width=1)
    cur_y += 25

    # 5. Steps Operation
    draw.text((PADDING, cur_y), "烹饪操作流程", fill=TEXT_MAIN, font=sec_font)
    cur_y += 44
    for line in op_lines:
        # Highlight step numbers e.g. "1." or "2."
        draw.text((PADDING + 10, cur_y), line, fill=TEXT_MAIN, font=body_font)
        cur_y += 34
    cur_y += 25

    # 6. Additional Notes
    if add_text:
        draw.line([(PADDING, cur_y), (WIDTH - PADDING, cur_y)], fill=BORDER_COLOR, width=1)
        cur_y += 25
        draw.text((PADDING, cur_y), "操作要点与安全须知", fill=TEXT_MAIN, font=sec_font)
        cur_y += 44
        for line in add_lines:
            draw.text((PADDING + 10, cur_y), line, fill=TEXT_MUTED, font=body_font)
            cur_y += 32
        cur_y += 25

    # 7. Footer
    draw.line([(PADDING, TOTAL_HEIGHT - PADDING - 45), (WIDTH - PADDING, TOTAL_HEIGHT - PADDING - 45)], fill=BORDER_COLOR, width=1)
    footer_text = "HowToCook 程序员做饭指南 · 严格工程化开源菜谱 · AstrBot 智能助手"
    draw.text((PADDING, TOTAL_HEIGHT - PADDING - 30), footer_text, fill=TEXT_MUTED, font=footer_font)

    img.save(str(output_file), format='PNG', optimize=True)
    return str(output_file)
