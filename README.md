# 🍳 程序员做饭指南 HowToCook · AstrBot 智能插件

> 把 GitHub 103k+ Star 的开源烹饪指南，变成你的全天候 AI 智能大厨伴侣。

[![AstrBot](https://img.shields.io/badge/AstrBot-v4.26%2B-blue)](https://github.com/Soulter/AstrBot)
[![Upstream](https://img.shields.io/badge/数据来源-HowToCook-orange)](https://github.com/Anduin2017/HowToCook)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](./LICENSE)
[![Python](https://img.shields.io/badge/Python-3.10%2B-brightgreen)](https://python.org)

---

## 📖 项目简介

`astrbot_plugin_howtocook` 是专为 [AstrBot](https://github.com/Soulter/AstrBot) 打造的现代化智能烹饪伴侣插件。

本插件深度融合了全网最著名的工程化开源菜谱项目 —— [Anduin2017/HowToCook](https://github.com/Anduin2017/HowToCook)（程序员做饭指南）。它用严谨的**面向对象思维、量化克数标准与状态判定**，彻底消除传统烹饪中“盐少许、生抽适量、玄学火候”的模糊痛点。

无论是精准查菜、输入人数自动放大用量、根据“冰箱剩余食材”逆向找菜，还是一键提取第三方（小红书/下厨房/B站等）链接重构为标准化菜谱，本插件都能在微信、QQ、Telegram 等聊天软件中为您提供清爽优雅的服务。

---

## ✨ 特性亮点

* **370+ 道官方工程化经典菜谱 + 19 篇技巧离线直出**  
  涵盖素菜、荤菜、水产、早餐、主食、汤羹、甜品及半成品深加工，内置全部数据，毫秒级快速检索，零外部网络依赖。
* **第三方链接一键收录与“量化重构”**  
  在聊天中分享任意第三方美食链接（小红书、下厨房、B站、公众号、博客等），插件自动提取干净正文，并通过大模型充当“Chef Linter”，将口语化、“适量/少许”等模糊文字强力重构为 HowToCook 4 段式精准量化标准（换算为克 `g`、毫升 `ml` 与明确时间/状态判定）。
* **多版本冲突自适应消解与官方库保护**  
  * **URL 幂等检查**：重复链接自动识别并指引已有菜名，避免算力浪费；
  * **官方库写保护**：官方 373 道经典菜永久只读保护，同名提交自动另存为新分支变体（如 `【可乐鸡翅·空气炸锅版】`）；
  * **自建库灵活管理**：支持多版本并存，亦支持 `--overwrite` 覆盖更新。
* **用餐人数用量线性缩放引擎**  
  根据用餐人数（例如输入 `4人份`），自动基于 1 盘/2 人份基准配方，按比例自动缩放原料克数、毫升数与调料比例。
* **智能“冰箱查菜”逆向匹配算法**  
  输入手头现有食材（如 `土豆 牛肉 番茄`），算法自动区分**核心主料**与**厨房常备调料**，计算主料覆盖率，优先推荐缺料最少、实现门槛最低的菜肴。
* **极简优雅长图海报排版（Pillow 渲染）**  
  采用暖色调卡片布局（温润米白背景 + 珊瑚橙强调色），自动排版生成高清菜谱长图卡片，聊天端美观大方，杜绝大段文字刷屏；自建菜谱自动印有专属 `⭐ 私房自建收录` 徽标。
* **双轨智能交互（Agent Function Calling + 快捷指令）**  
  既支持快捷斜杠指令直达，又无缝向 AstrBot 中枢大模型注册标准 LLM Tools，自然语言聊天时自动唤醒。

---

## 🚀 安装部署

### 方法一：通过 Git 克隆至 AstrBot 插件目录（推荐）

进入您的 AstrBot `data/plugins/` 目录，执行克隆：

```bash
cd /path/to/AstrBot/data/plugins/
git clone https://github.com/zclin0512/astrbot_plugin_howtocook.git
```

克隆完成后，重启 AstrBot 容器或在 WebUI 重新加载插件即可生效。

### 方法二：手动下载解压

1. 下载本仓库的源码或 Release 压缩包；
2. 解压并将文件夹重命名为 `astrbot_plugin_howtocook`；
3. 将该目录放置于 AstrBot 的 `data/plugins/` 目录下；
4. 重启 AstrBot 即可。

---

## 📖 指令手册

| 指令 | 别名 | 功能说明 | 示例 |
| :--- | :--- | :--- | :--- |
| `/做菜 <菜名> [人数]` | `/菜谱`, `/howtocook` | 精准查询指定菜谱及做法，支持人数缩放 | `/做菜 可乐鸡翅 4人份` |
| `/存菜谱 <URL> [自定义名]` | `/收录`, `/导入菜谱` | 提取第三方链接并智能重构入库出图 | `/存菜谱 https://xhslink.com/xxx 奥尔良烤翅` |
| `/我的菜谱` | `/自建菜谱`, `/收录列表` | 查看已收录的自建私房菜谱列表与来源 | `/我的菜谱` |
| `/删除菜谱 <菜名>` | `/del_recipe` | 从私房库中删除指定菜谱（官方菜谱受保护不可删） | `/删除菜谱 可乐鸡翅·空气炸锅版` |
| `/吃什么 [分类/难度]` | `/今天吃什么`, `/吃啥` | 随机推荐一道菜，解决纠结 | `/吃什么 荤菜 3星` |
| `/冰箱 <食材...>` | `/查食材`, `/做啥菜` | 根据手头现有食材反向推荐最合适菜品 | `/冰箱 土豆 牛肉 番茄` |
| `/厨房技巧 <关键词>` | `/下厨技巧`, `/做菜技巧` | 查询焯水、去腥、刀工等基础技巧指南 | `/厨房技巧 焯水` |
| `/做菜模式 [card/text]` | `/howtocook_mode` | 切换当前会话优先输出海报卡片还是纯文本 | `/做菜模式 card` |

> 💬 **支持免斜杠自然语言口语直达**：
> * `想吃可乐鸡翅 4人份`
> * `今天吃什么`
> * `冰箱里有西红柿和鸡蛋，可以做什么菜？`
> * `存一下这个菜谱 https://www.xiachufang.com/recipe/xxxx/`

---

## 🤖 大模型 Agent 工具 (Function Calling)

插件向 AstrBot 注册了 5 个标准 Agent Tools，大模型在分析用户对话意图时会自动调起：

1. `howtocook_get_recipe(dish_name, servings, send_card_image)`  
   获取指定菜谱的详尽原料、换算克数及分步操作规范，并可选直接发送高清长图卡片。
2. `howtocook_import_recipe_from_url(url, custom_name, overwrite)`  
   当用户在自然对话中分享第三方链接并希望记下或学习时，自动完成内容抓取、大模型量化重构与入库。
3. `howtocook_recommend_by_ingredients(ingredients, limit)`  
   根据用户现有的食材数组进行逆向配菜分析，输出匹配主料与缺失需补充主料。
4. `howtocook_random_dish(category, max_difficulty)`  
   根据分类与难度偏好随机选菜。
5. `howtocook_get_tips(keyword)`  
   检索厨房与烹饪基础技巧（焯水、去腥、刀工、油温、微波炉、高压锅等）。

---

## ⚙️ 配置项说明

在 AstrBot WebUI 插件管理面板或 `_conf_schema.json` 中可自定义以下选项：

| 配置键 | 类型 | 默认值 | 说明 |
| :--- | :--- | :--- | :--- |
| `output_format` | string | `"card"` | 默认输出形式：`card`（长图海报，推荐防刷屏）或 `text`（纯文本） |
| `default_servings` | int | `2` | 默认基准用餐人数 |
| `max_recommendations` | int | `5` | 冰箱查菜时最多推荐的菜品数量 |
| `custom_font_path` | string | `""` | 可选自定义容器内中文字体路径，留空则自动检测系统中文字体 |

---

## 🔗 引用与致谢

本插件由衷感谢以下开源项目与服务提供的坚实基石：

* 🌟 **数据源基石**：[Anduin2017/HowToCook](https://github.com/Anduin2017/HowToCook) —— 程序员在家做饭方法指南。感谢原作者 **Anduin2017** 及数百位开源共创者整理的高质量量化菜谱数据（遵循 [The Unlicense](https://github.com/Anduin2017/HowToCook/blob/master/LICENSE) 协议）。
* 🤖 **机器人框架**：[Soulter/AstrBot](https://github.com/Soulter/AstrBot) —— 易用、高扩展的多平台大模型聊天机器人中枢框架。
* 🌐 **网页净化解析**：[Jina Reader API](https://jina.ai/reader/) —— 为大模型提供优质免反爬网页转 Markdown 提取服务。

---

## 📄 开源许可证

本项目核心代码采用 [MIT License](./LICENSE) 开源协议；  
包含的官方菜谱数据源遵循原项目的 [The Unlicense](https://github.com/Anduin2017/HowToCook/blob/master/LICENSE) 公有领域许可证。
