"""Dataset builder for HowToCook AstrBot Plugin.
Parses dishes and tips from HowToCook repository into clean, structured JSON files.
"""

import glob
import json
import os
import re

CATEGORY_MAP = {
    'vegetable_dish': '素菜',
    'meat_dish': '荤菜',
    'aquatic': '水产',
    'breakfast': '早餐',
    'staple': '主食',
    'semi-finished': '半成品加工',
    'soup': '汤与粥',
    'drink': '饮料',
    'condiment': '酱料',
    'dessert': '甜品',
}

COMMON_TOOLS = {
    '盆', '盘子', '菜刀', '锅', '炒锅', '量杯', '厨房秤', '密封袋',
    '刷子', '笊篱', '筷子', '保鲜膜', '吸水纸', '烤箱', '微波炉',
    '空气炸锅', '打蛋器', '滤网', '锡纸', '保鲜盒', '蒸锅', '高压锅'
}

COMMON_PANTRY = {
    '油', '食用油', '植物油', '花生油', '菜籽油', '玉米油', '橄榄油', '猪油',
    '盐', '食用盐', '细盐', '粗盐',
    '水', '饮用水', '清水', '热水', '开水', '温水', '凉水',
    '生抽', '老抽', '酱油', '蒸鱼豉油',
    '料酒', '黄酒', '白酒', '啤酒',
    '糖', '白糖', '白砂糖', '冰糖', '红糖',
    '醋', '白醋', '陈醋', '香醋', '米醋',
    '鸡精', '味精', '耗油', '蚝油',
    '淀粉', '生粉', '玉米淀粉',
    '葱', '大葱', '小葱', '香葱', '葱花', '葱段', '青葱',
    '姜', '生姜', '老姜', '姜片', '姜末', '姜丝',
    '蒜', '大蒜', '蒜瓣', '蒜末', '蒜泥',
    '胡椒粉', '黑胡椒', '白胡椒', '白胡椒粉', '黑胡椒粉',
    '花椒', '花椒粉', '八角', '桂皮', '香叶', '干辣椒'
}

SOURCE_DIR = '/tmp/HowToCook'
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), 'data')


def clean_ingredient_items(raw_lines: list[str]) -> tuple[list[str], list[str]]:
    """Separates ingredients into main items (core) and pantry seasoning items."""
    main_items = []
    pantry_items = []

    for raw in raw_lines:
        line = raw.strip()
        if not line or line.startswith(('注：', '注意：', '提示：', '参考：', '工具：', '<!--')):
            continue
        # Remove comments, parens, markdown formatting
        cleaned = re.sub(r'<!--.*?-->', '', line)
        cleaned = re.sub(r'[\(（].*?[\)）]', '', cleaned)
        cleaned = re.sub(r'[*_`#]', '', cleaned)

        # Split multiple ingredients on same line
        parts = re.split(r'[,，、/或;；\s]+', cleaned)
        for p in parts:
            p = p.strip()
            # Remove trailing quantity numbers if any
            p = re.sub(r'\d+.*$', '', p).strip()
            for qualifier in ['适量', '少许', '可选', '少量', '推荐品牌', '一个', '一颗', '一条', '两只', '若干', '少许']:
                p = p.replace(qualifier, '').strip()

            if not p or len(p) > 10:
                continue
            if any(tool in p for tool in COMMON_TOOLS):
                continue

            if p in COMMON_PANTRY:
                if p not in pantry_items:
                    pantry_items.append(p)
            else:
                if p not in main_items:
                    main_items.append(p)

    return main_items, pantry_items


def parse_dish(p: str) -> dict:
    rel = os.path.relpath(p, os.path.join(SOURCE_DIR, 'dishes'))
    cat = rel.split(os.sep)[0]
    dish_name = os.path.splitext(os.path.basename(p))[0]
    with open(p, 'r', encoding='utf-8') as f:
        content = f.read()

    # Title
    title_m = re.search(r'^#\s*(.*?)(?:的做法)?\s*$', content, re.M)
    title = title_m.group(1).strip() if title_m else dish_name

    # Difficulty & Calories
    diff_m = re.search(r'预估烹饪难度：\s*(★+)', content)
    difficulty = len(diff_m.group(1)) if diff_m else 2
    cal_m = re.search(r'预估卡路里：\s*(\d+)', content)
    calories = int(cal_m.group(1)) if cal_m else None

    # Sections
    sections = re.split(r'\n##\s+', '\n' + content)
    intro = sections[0].strip() if len(sections) > 0 else ''

    intro_lines = []
    for line in intro.splitlines():
        line = line.strip()
        if not line or line.startswith('#') or line.startswith('预估') or line.startswith('![') or line.startswith('<!--'):
            continue
        intro_lines.append(line)
    description = '\n'.join(intro_lines).strip()

    sec_map = {}
    for sec in sections[1:]:
        lines = sec.splitlines()
        sec_title = lines[0].strip()
        sec_body = '\n'.join(lines[1:]).strip()
        sec_map[sec_title] = sec_body

    # Raw ingredients
    raw_ing = sec_map.get('必备原料和工具', '')
    raw_lines = []
    for line in raw_ing.splitlines():
        line = line.strip()
        m = re.match(r'^[-*+]\s*(.+)$', line)
        if m:
            raw_lines.append(m.group(1).strip())

    main_ingredients, pantry_ingredients = clean_ingredient_items(raw_lines)
    all_ingredients = main_ingredients + [p for p in pantry_ingredients if p not in main_ingredients]

    # Calculation
    calculation = sec_map.get('计算', '')
    # Operation
    operation = sec_map.get('操作', '')
    clean_op_lines = []
    for line in operation.splitlines():
        if line.strip().startswith('![') or line.strip().startswith('<!--'):
            continue
        clean_op_lines.append(line)
    clean_operation = '\n'.join(clean_op_lines).strip()

    # Additional
    additional = sec_map.get('附加内容', '')
    clean_add_lines = []
    for line in additional.splitlines():
        if '如果您遵循本指南' in line or '提出 Issue' in line or line.strip().startswith('<!--'):
            continue
        clean_add_lines.append(line)
    clean_additional = '\n'.join(clean_add_lines).strip()

    # Base servings detection from calculation
    base_servings = 2
    servings_m = re.search(r'(\d+)\s*(?:人|份|个人)', calculation)
    if servings_m:
        try:
            base_servings = int(servings_m.group(1))
        except ValueError:
            base_servings = 2

    return {
        'id': dish_name,
        'name': dish_name,
        'title': title,
        'category': cat,
        'category_name': CATEGORY_MAP.get(cat, '其他'),
        'difficulty': difficulty,
        'calories': calories,
        'description': description,
        'main_ingredients': main_ingredients,
        'pantry_ingredients': pantry_ingredients,
        'ingredients': all_ingredients,
        'base_servings': base_servings,
        'calculation': calculation,
        'operation': clean_operation,
        'additional': clean_additional,
    }


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    dishes = []
    for p in sorted(glob.glob(os.path.join(SOURCE_DIR, 'dishes/**/*.md'), recursive=True)):
        if 'template' in p:
            continue
        d = parse_dish(p)
        dishes.append(d)

    tips = []
    for p in sorted(glob.glob(os.path.join(SOURCE_DIR, 'tips/**/*.md'), recursive=True)):
        name = os.path.splitext(os.path.basename(p))[0]
        with open(p, 'r', encoding='utf-8') as f:
            content = f.read()
        content = re.sub(r'<!--.*?-->', '', content, flags=re.DOTALL).strip()
        tips.append({
            'name': name,
            'path': os.path.relpath(p, os.path.join(SOURCE_DIR, 'tips')),
            'content': content
        })

    with open(os.path.join(OUTPUT_DIR, 'recipes.json'), 'w', encoding='utf-8') as f:
        json.dump(dishes, f, ensure_ascii=False, indent=2)

    with open(os.path.join(OUTPUT_DIR, 'tips.json'), 'w', encoding='utf-8') as f:
        json.dump(tips, f, ensure_ascii=False, indent=2)

    print(f'Successfully rebuilt dataset:')
    print(f'  - Recipes: {len(dishes)} dishes')
    print(f'  - Tips: {len(tips)} articles')


if __name__ == '__main__':
    main()
