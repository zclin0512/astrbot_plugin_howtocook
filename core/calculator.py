"""Ingredient and serving scale calculator for HowToCook recipes.
Dynamically scales ingredient quantities according to requested servings.
"""

from __future__ import annotations

import re


def _scale_number(val_str: str, factor: float) -> str:
    try:
        val = float(val_str)
        scaled = val * factor
        # If integer or close to integer, format as int
        if abs(scaled - round(scaled)) < 0.05:
            return str(int(round(scaled)))
        # Otherwise keep 1 decimal place
        return f"{scaled:.1f}"
    except ValueError:
        return val_str


def scale_calculation(calc_text: str, base_servings: int, target_servings: int) -> str:
    """Scales quantities in the calculation section of a recipe.

    Args:
        calc_text: The markdown text under '## 计算'.
        base_servings: Original servings baseline (usually 1 or 2).
        target_servings: Desired servings (e.g. 4).

    Returns:
        A formatted markdown string reflecting the scaled quantities.
    """
    if not calc_text or target_servings <= 0 or base_servings <= 0 or target_servings == base_servings:
        return calc_text

    factor = target_servings / float(base_servings)
    lines = calc_text.splitlines()
    scaled_lines = []

    # Units to match: g, kg, ml, l, 毫升, 克, 千克, 斤, 两, 个, 只, 块, 瓣, 根, 勺, 匙, 片, 碗, 杯, 听, 罐, 瓶
    unit_pattern = r'(g|kg|ml|l|毫升|升|克|千克|斤|两|个|只|块|瓣|根|勺|匙|片|碗|杯|听|罐|瓶|袋|包)'

    for line in lines:
        stripped = line.strip()
        # Header indicator like "每份：" or "按照 1 盘："
        if re.search(r'(每份|按照\s*\d+\s*盘|份量|人数)', stripped):
            scaled_lines.append(f"**已自适应换算为 {target_servings} 人份用量（原方基准 {base_servings} 人份，缩放倍率 ×{factor:.2g}）：**")
            continue

        if not stripped.startswith(('*', '-', '+')):
            scaled_lines.append(line)
            continue

        # Try to match ranges like "10 ～ 12 只" or "10-15g"
        def replace_range(match):
            n1 = _scale_number(match.group(1), factor)
            sep = match.group(2)
            n2 = _scale_number(match.group(3), factor)
            suffix = match.group(4)
            return f"{n1}{sep}{n2}{suffix}"

        scaled_line = re.sub(
            rf'(\d+(?:\.\d+)?)\s*([~～\-–到])\s*(\d+(?:\.\d+)?)\s*({unit_pattern})',
            replace_range,
            line,
            flags=re.IGNORECASE
        )

        # Match single numbers with units like "500ml", "10 克"
        def replace_single(match):
            n = _scale_number(match.group(1), factor)
            space = match.group(2)
            unit = match.group(3)
            return f"{n}{space}{unit}"

        # Avoid replacing already replaced ranges by matching remaining patterns
        scaled_line = re.sub(
            rf'(?<![~～\-–到\d])(\d+(?:\.\d+)?)\s*({unit_pattern})',
            lambda m: f"{_scale_number(m.group(1), factor)} {m.group(2)}",
            scaled_line,
            flags=re.IGNORECASE
        )

        scaled_lines.append(scaled_line)

    return '\n'.join(scaled_lines)
