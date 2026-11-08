"""Recipe and Tips database engine for HowToCook plugin.
Provides indexing, exact/fuzzy search, ingredient matching, layered custom recipe persistence,
and multi-version conflict resolution.
"""

from __future__ import annotations

import datetime
import hashlib
import json
import os
import random
import re
from typing import Any, Dict, List, Optional, Tuple


CATEGORY_NAMES = {
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

CATEGORY_ALIAS = {
    '素菜': 'vegetable_dish',
    '青菜': 'vegetable_dish',
    '蔬菜': 'vegetable_dish',
    '荤菜': 'meat_dish',
    '肉': 'meat_dish',
    '肉菜': 'meat_dish',
    '水产': 'aquatic',
    '海鲜': 'aquatic',
    '鱼': 'aquatic',
    '虾': 'aquatic',
    '早餐': 'breakfast',
    '早饭': 'breakfast',
    '主食': 'staple',
    '米饭': 'staple',
    '面条': 'staple',
    '半成品': 'semi-finished',
    '预制菜': 'semi-finished',
    '汤': 'soup',
    '粥': 'soup',
    '汤与粥': 'soup',
    '饮料': 'drink',
    '饮品': 'drink',
    '甜品': 'dessert',
    '甜点': 'dessert',
    '酱料': 'condiment',
    '调味': 'condiment',
}


class RecipeDB:
    def __init__(self, data_dir: Optional[str] = None):
        if data_dir is None:
            data_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data')
        self.data_dir = data_dir
        self.custom_file = os.path.join(self.data_dir, 'custom_recipes.json')
        self.recipes: List[Dict[str, Any]] = []
        self.official_recipes: List[Dict[str, Any]] = []
        self.custom_recipes: List[Dict[str, Any]] = []
        self.recipe_map: Dict[str, Dict[str, Any]] = {}
        self.tips: List[Dict[str, Any]] = []
        self.tip_map: Dict[str, Dict[str, Any]] = {}
        self._load()

    def _load(self):
        recipes_path = os.path.join(self.data_dir, 'recipes.json')
        tips_path = os.path.join(self.data_dir, 'tips.json')

        self.official_recipes = []
        self.custom_recipes = []
        self.recipes = []
        self.recipe_map = {}

        # 1. Load official read-only baseline
        if os.path.exists(recipes_path):
            with open(recipes_path, 'r', encoding='utf-8') as f:
                self.official_recipes = json.load(f)
            for r in self.official_recipes:
                r['is_official'] = True
                r['is_custom'] = False
                self._index_recipe(r)

        # 2. Load custom user-contributed recipes
        if os.path.exists(self.custom_file):
            try:
                with open(self.custom_file, 'r', encoding='utf-8') as f:
                    self.custom_recipes = json.load(f)
                for r in self.custom_recipes:
                    r['is_official'] = False
                    r['is_custom'] = True
                    self._index_recipe(r)
            except Exception as e:
                print(f"Failed to load custom recipes: {e}")

        self.recipes = self.official_recipes + self.custom_recipes

        # 3. Load tips
        if os.path.exists(tips_path):
            with open(tips_path, 'r', encoding='utf-8') as f:
                self.tips = json.load(f)
            for t in self.tips:
                self.tip_map[t['name']] = t

    def _index_recipe(self, r: Dict[str, Any]):
        self.recipe_map[r['name']] = r
        if 'id' in r:
            self.recipe_map[r['id']] = r
        clean_name = re.sub(r'的做法$', '', r['name']).strip()
        self.recipe_map[clean_name] = r

    def normalize_category(self, cat: Optional[str]) -> Optional[str]:
        if not cat:
            return None
        cat_clean = cat.strip().lower()
        if cat_clean in CATEGORY_NAMES:
            return cat_clean
        return CATEGORY_ALIAS.get(cat_clean)

    def check_url_exists(self, url: str) -> Optional[Dict[str, Any]]:
        """Checks if a URL has already been imported (L1 deduplication)."""
        if not url:
            return None
        target = url.strip()
        for r in self.custom_recipes:
            if r.get('source_url', '').strip() == target:
                return r
        return None

    def check_collision(self, name: str) -> Tuple[str, Optional[Dict[str, Any]]]:
        """Checks if recipe name collides with official or custom recipes (L2 deduplication).

        Returns:
            ("OFFICIAL", existing_recipe) or ("CUSTOM", existing_recipe) or ("NONE", None)
        """
        clean = re.sub(r'(的做法|的做菜指南|菜谱|指南)$', '', name.strip())
        for r in self.official_recipes:
            if r['name'] == clean or r['name'] == name.strip():
                return "OFFICIAL", r
        for r in self.custom_recipes:
            if r['name'] == clean or r['name'] == name.strip():
                return "CUSTOM", r
        return "NONE", None

    def get_variants(self, name: str) -> List[Dict[str, Any]]:
        """Finds all variants of a dish (e.g. official + airfryer + microwave)."""
        clean = re.sub(r'(的做法|的做菜指南|菜谱|指南)$', '', name.strip())
        variants = []
        for r in self.recipes:
            r_clean = re.sub(r'(的做法|的做菜指南|菜谱|指南)$', '', r['name'])
            if r_clean == clean or r_clean.startswith(f"{clean}·") or r_clean.startswith(f"{clean} (") or clean in r_clean:
                variants.append(r)
        return variants

    def save_custom_recipe(
        self,
        recipe_dict: Dict[str, Any],
        overwrite: bool = False,
        resolve_mode: str = "variant"
    ) -> Tuple[Dict[str, Any], str]:
        """Saves a custom recipe with conflict handling.

        Args:
            recipe_dict: structured recipe object.
            overwrite: whether to overwrite if collision with custom recipe.
            resolve_mode: 'variant' (rename as variant), 'overwrite' (replace custom only).

        Returns:
            (saved_recipe, status_message)
        """
        name = recipe_dict.get('name', '未命名菜品').strip()
        variant_tag = recipe_dict.get('variant_tag', '').strip()
        collision_type, existing = self.check_collision(name)

        final_name = name
        status_msg = "新增入库"

        if collision_type == "OFFICIAL":
            # Official recipes are IMMUTABLE. Always save as variant
            tag = variant_tag or "私房版"
            final_name = f"{name}·{tag}"
            status_msg = f"官方版已保护，自动另存为变体版本【{final_name}】"
        elif collision_type == "CUSTOM":
            if overwrite or resolve_mode == "overwrite":
                # Overwrite existing custom
                self.custom_recipes = [r for r in self.custom_recipes if r['name'] != name and r.get('id') != existing.get('id')]
                status_msg = f"已成功覆盖原自建版本【{name}】"
            else:
                tag = variant_tag or f"版本{len(self.get_variants(name)) + 1}"
                final_name = f"{name}·{tag}"
                status_msg = f"自建重名，自动另存为新版本【{final_name}】"

        recipe_dict['name'] = final_name
        recipe_dict['title'] = final_name
        if not recipe_dict.get('id'):
            url_hash = hashlib.md5(recipe_dict.get('source_url', final_name).encode('utf-8')).hexdigest()[:8]
            recipe_dict['id'] = f"custom_{final_name}_{url_hash}"

        recipe_dict['is_official'] = False
        recipe_dict['is_custom'] = True
        recipe_dict['category_name'] = CATEGORY_NAMES.get(recipe_dict.get('category'), '家常菜')
        recipe_dict['created_at'] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Append to custom list and persist
        self.custom_recipes.append(recipe_dict)
        with open(self.custom_file, 'w', encoding='utf-8') as f:
            json.dump(self.custom_recipes, f, ensure_ascii=False, indent=2)

        # Refresh in-memory indexes
        self._load()
        return recipe_dict, status_msg

    def delete_custom_recipe(self, name_or_id: str) -> bool:
        """Deletes a custom recipe by name or ID."""
        target = name_or_id.strip()
        initial_len = len(self.custom_recipes)
        self.custom_recipes = [
            r for r in self.custom_recipes
            if r['name'] != target and r.get('id') != target and r['name'] != target.replace('的做法', '')
        ]
        if len(self.custom_recipes) < initial_len:
            with open(self.custom_file, 'w', encoding='utf-8') as f:
                json.dump(self.custom_recipes, f, ensure_ascii=False, indent=2)
            self._load()
            return True
        return False

    def list_custom_recipes(self) -> List[Dict[str, Any]]:
        """Returns all custom saved recipes."""
        return list(self.custom_recipes)

    def get_recipe(self, name: str) -> Optional[Dict[str, Any]]:
        """Finds recipe by exact name, normalized name, or best substring."""
        if not name:
            return None
        token = name.strip()
        token_clean = re.sub(r'^(我想做|怎么做|教我做|做道|做个|做|吃|看|查)\s*', '', token)
        token_clean = re.sub(r'(的做法|的做菜指南|菜谱|指南)$', '', token_clean).strip()

        # 1. Exact match in recipe_map (custom overrides or matches)
        if token_clean in self.recipe_map:
            return self.recipe_map[token_clean]

        # 2. Prefer custom variant if user explicitly asked for variant
        for r in self.custom_recipes:
            if token_clean == r['name']:
                return r

        # 3. Substring match
        matches = []
        for r in self.recipes:
            if r['name'] == token_clean:
                return r
            if token_clean in r['name'] or r['name'] in token_clean:
                matches.append(r)

        if matches:
            matches.sort(key=lambda x: (not x.get('is_custom', False), abs(len(x['name']) - len(token_clean))))
            return matches[0]

        return None

    def search_recipes(
        self,
        keyword: str = '',
        category: Optional[str] = None,
        max_difficulty: Optional[int] = None,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """Searches recipes with optional category and difficulty filtering."""
        cat_filter = self.normalize_category(category)
        kw = keyword.strip().lower() if keyword else ''

        results = []
        for r in self.recipes:
            if cat_filter and r['category'] != cat_filter:
                continue
            if max_difficulty and r['difficulty'] > max_difficulty:
                continue

            if not kw:
                results.append((r, 1))
                continue

            score = 0
            name_lower = r['name'].lower()
            if kw == name_lower:
                score += 100
            elif kw in name_lower:
                score += 50
            elif any(kw in ing.lower() for ing in r['ingredients']):
                score += 20
            elif kw in r['description'].lower():
                score += 10

            if score > 0:
                results.append((r, score))

        results.sort(key=lambda x: -x[1])
        return [item[0] for item in results[:limit]]

    def match_by_ingredients(
        self,
        user_ingredients: List[str],
        limit: int = 5,
        category: Optional[str] = None,
        max_difficulty: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """Intelligent ingredient-based reverse recipe matching."""
        cat_filter = self.normalize_category(category)
        cleaned_user_ings = [u.strip() for u in user_ingredients if u.strip()]
        if not cleaned_user_ings:
            return []

        scored_items = []
        for r in self.recipes:
            if cat_filter and r['category'] != cat_filter:
                continue
            if max_difficulty and r['difficulty'] > max_difficulty:
                continue

            main_ings = r.get('main_ingredients', [])
            pantry_ings = r.get('pantry_ingredients', [])

            matched_main = []
            missing_main = []
            for ing in main_ings:
                if any(u in ing or ing in u for u in cleaned_user_ings):
                    matched_main.append(ing)
                else:
                    missing_main.append(ing)

            matched_pantry = []
            for ing in pantry_ings:
                if any(u in ing or ing in u for u in cleaned_user_ings):
                    matched_pantry.append(ing)

            matched_all = matched_main + matched_pantry
            if not matched_all:
                continue

            total_main = max(len(main_ings), 1)
            main_ratio = len(matched_main) / total_main
            score = (main_ratio * 70.0) + (len(matched_main) * 15.0) + (len(matched_pantry) * 3.0) - (len(missing_main) * 8.0)

            scored_items.append({
                'recipe': r,
                'score': score,
                'matched_main': matched_main,
                'missing_main': missing_main,
                'matched_pantry': matched_pantry,
                'matched_all': matched_all,
                'main_coverage': round(main_ratio * 100, 1),
            })

        scored_items.sort(key=lambda x: (-x['score'], len(x['missing_main']), -x['main_coverage']))
        return scored_items[:limit]

    def random_dish(
        self,
        category: Optional[str] = None,
        max_difficulty: Optional[int] = None
    ) -> Optional[Dict[str, Any]]:
        """Picks a random dish matching the criteria."""
        cat_filter = self.normalize_category(category)
        pool = []
        for r in self.recipes:
            if cat_filter and r['category'] != cat_filter:
                continue
            if max_difficulty and r['difficulty'] > max_difficulty:
                continue
            pool.append(r)

        return random.choice(pool) if pool else None

    def search_tips(self, keyword: str = '') -> List[Dict[str, Any]]:
        """Searches kitchen tips and preparation knowledge."""
        kw = keyword.strip().lower() if keyword else ''
        if not kw:
            return self.tips

        matches = []
        for t in self.tips:
            name_lower = t['name'].lower()
            content_lower = t['content'].lower()
            if kw == name_lower:
                matches.append((t, 100))
            elif kw in name_lower:
                matches.append((t, 50))
            elif kw in content_lower:
                matches.append((t, 20))

        matches.sort(key=lambda x: -x[1])
        return [m[0] for m in matches]

    def get_tip(self, name_or_kw: str) -> Optional[Dict[str, Any]]:
        results = self.search_tips(name_or_kw)
        return results[0] if results else None
