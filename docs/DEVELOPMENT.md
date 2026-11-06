# 开发交接文档（chinese-novel-translator）

> 写给接手开发的人或 AI。读完这份文档，应该能在不翻聊天记录的情况下继续开发。
> 最后更新：2026-11-06，对应版本 **v0.9.0**（日语版第 1 步已完成，尚未发布）。

## 1. 项目是什么

- 一个 agent skill：用户把中文网文（.txt / .epub）交给自己的 AI agent，agent 按 `SKILL.md` 逐段翻成英文（v0.9.0 起可选日语：`init --lang ja`），输出 .epub / .html / .md。
- 仓库：https://github.com/LingHan-233/chinese-novel-translator （公开，MIT，署名 LingHan-233）。
- 维护者（LingHan-233）计划在 X 上推荐中文小说，并把这个工具分享给海外读者自己翻译阅读。
- 维护者的情况：中文母语，**英语不太好**，不是程序员。沟通用中文，解释要通俗；英文质量无法亲自判断，所以依赖"另一个模型修改 + 中文复述核对"。
- 维护者的测试环境：**WorkBuddy**（agent）+ **DeepSeek V4.1 Flash**（翻译模型）；另有 **Gemini 3.8 Flash**（思考强度：高）用来改示例。测试方式：开发方写提示词 → 维护者发给 WorkBuddy → WorkBuddy 产出 md 报告 → 维护者把报告拿回来评审。这个循环效果很好，继续沿用。
- 维护者正在用它翻译一本 1283 章 / 2509 个 passage / 约 270 万字的修仙网文（测试里叫"真书"）。

## 2. 核心设计原则（每一条都来自实测，改动前请先想清楚）

1. **模型只管翻译，脚本管记账和检查。** 便宜的 flash 模型单句翻译不差，但记不住长书，也不守复杂流程。所以每段生成一个自包含的任务文件，每条命令结尾都打印 `NEXT:` 告诉 agent 下一步。
2. **检查只能管格式和一致性，管不了意思。** "检查通过"不等于译对了。意思错误靠复核（review）。
3. **复核默认全量开启（`review full`）。** 埋错测试：全量复核 7/7 抓到；抽查复核只覆盖约 1/4 段落，抓到 6/24；不复核约每 20 段有 1 处意思错误。
4. **示例比规则有效得多。** 3 段本书示例改动了下一章 76% 的段落；十几条新规则只改动了 8%。但示例会让模型模仿过头（加戏、丢感叹号），所以示例和复核要一起用，示例要覆盖不同类型（对话、平静叙述、动作），选中等强度的段落。
5. **不要为了消警告把正确译文改坏。** 曾经出现模型为消除数字警告把准确的 "eight in ten" 改成含糊说法。警告都是提示，文案里写明"如果译文没错就保留"。
6. **替代词（谐音/委婉替代，如 牛至=牛子）：默认按字面意思，词表是提示，书的语境是裁判。** 同一个词在一本书里是梗，在另一本里是字面意思。误判（把正常词当梗）比漏判更糟，所以拿不准的一律交给人。
7. **术语表只放名字和反复出现的专名。** 普通词、单字（"道"会命中"一道菜"）会造成误报。
8. **不在仓库、帖子里放受版权保护的小说原文或译文。** 测试书都是原创文字。测试报告（含真书原文）绝不上传。

## 3. 文件结构

| 路径 | 作用 |
|---|---|
| `SKILL.md` | 给 agent 的操作说明（第 0–5 步 + 命令表） |
| `AGENTS.md` | 让不支持 skill 的 agent 也能找到 SKILL.md |
| `scripts/novel.py` | 全部逻辑，约 2810 行，只用 Python 标准库，3.8+ |
| `core/translation_rules.md`、`core/names.md` | 每个任务文件都会附带的翻译规则、专名规则 |
| `genres/*.md` | 题材模块：general / xianxia / urban / historical |
| `lang/en/style_guide.md`、`lang/en/examples.md` | 英文风格和通用示例（带题材标签） |
| `lang/ja/` | 日语版：`translation_rules.md`、`names.md`、`style_guide.md`、`genres/xianxia.md`、`genres/general.md`（**草稿，未经懂日语的人核对**）；还没有 `examples.md` |
| `slang/zh_internet_slang.tsv` | 共享用语表，6 列：term, meaning, tone, default_en, strategy, avoid（tone 含 `stand-in` 表示替代词；avoid = 要避免的字面英文） |
| `templates/` | 空白术语表、角色表、梗概 |
| `tests/sample_book.txt` | 原创示例小说，试跑流程用 |
| `tests/scan_sample_a.txt` / `_b.txt` | 替代词误判测试用的原创短篇（标准答案不在仓库里，见第 6 节） |
| `tests/inject_errors.py` | 在译文里埋意思错误，测试复核能不能抓到 |
| `tests/workflow_run.py` | 用假译文把整个流程（init → 扫描 → 翻译/检查/复核/accept → 试译停止 → pin → rename/redo → build）跑一遍，记录每条命令的输出和每个任务文件。改代码后用新旧两个版本各跑一遍再 diff，确认英文版没被改坏（用法见文件开头） |
| `VERSION` | 版本号，需与 `novel.py` 里的 `VERSION` 一致 |

**语言相关文件的查找规则**（`lang_text` / `genre_text`）：任务文件先找 `lang/<语言>/` 下的同名文件；英文没有自己的 `translation_rules.md` / `names.md`，用 `core/` 的；英文题材用 `genres/`，其他语言只用 `lang/<语言>/genres/`，没有就显示"暂无该题材说明"（英文题材说明里全是英文译法，不能给日语用）。

用户的工作区（不进仓库，`.gitignore` 已排除）：`novel-translations/<书>/`，里面有 `book.json`、`source/`、`translated/`、`work/`（当前任务、输出、笔记）、`bible/`（glossary.tsv、characters.tsv、slang_extra.tsv、slang_off.txt、scan_done.tsv、examples.md、flags.tsv、conflicts.tsv、synopsis.md）、`output/`。

## 4. 命令一览（`novel.py --help`）

init, candidates, scan, scan-apply, add, next, check, review(=polish), accept, status, set, pin, flags, set-char, rename, skip, unskip, redo, build。

- `init --lang en|ja`：目标语言，存在 `book.json` 的 `target_lang`（默认 en）。
- `set lang ja`：只能在还没翻译、术语表和角色表都空的时候改。
- `set keep_chars 玥`：日语书专用，允许某个日语里没有的字留在译文里（只给人名用；`none` 清空）。

主流程：`init` → `candidates` + 写 CHAR/TERM/SLANG 行 → `add` → `scan` → 写 VERDICT → `scan-apply` → 循环 [`next` → 翻译 → `check` → `review` → `check` → 写笔记 → `accept`] → 第一章后试译停止（`pin` 示例、问用户）→ `set trial false` → 继续 → `build`。

笔记行格式：`SUMMARY:`、`TERM: 中文 | English | type | note`、`CHAR: 中文 | English | gender | note | 别名/别名`、`SLANG: 中文 | meaning | tone | English | how | avoid`、`NOSLANG: 词`、`FLAG: P10 | 原因`。
扫描结论格式：`VERDICT: 词 | stand-in/vulgar/literal/unsure | high/low | ...`。

## 5. 版本历史与测试结论

| 版本 | 主要内容 | 测试结论 |
|---|---|---|
| 第一～三版（内部） | 骨架、目录跳过、试译、复核、`rename` | 流程在 WorkBuddy 跑通；同模型自评会漏掉真错误 |
| v0.6.x | 数字检查、示例 `pin --en`、误报修复、MIT、首次公开发布 | 261 段复核改 34 段，其中 13 处是意思错误 |
| v0.7.0 | 替代词：共享表加 avoid 列、SLANG 行、字面直译警告 | 已登记的词全部能抓；未登记的仍静默 |
| v0.7.1–0.7.2 | 全书叠词扫描、NOSLANG、"俩/双"数字误报 | 按频次排序在整本书上失效，改为按"像不像名词"排序 + 附例句 |
| v0.8.0 | `scan`：模型结合多处例句判断替代词 | 两本测试书 + 真书 60 词：**零误判**，目标词全部判对 |
| v0.8.1 | 例句优先选整词、`vulgar` 档、固定梗一句可判 | 未单独重测（改动小） |
| v0.9.0 | 日语版第 1 步：`--lang`、按语言分开的检查、日语草稿说明、成书的语言标签 | 英文版：新旧两版用 `tests/workflow_run.py` 跑完整流程，任务文件、复核文件、bible、成书完全相同，只多一行"Translating into"提示。日语版：只用假译文跑通流程，**还没让真模型翻过** |

各轮测试报告由维护者保管，没有放进仓库（含真书原文）。

## 6. 已知问题与未验证的部分

- **没有从头连续翻过几百章**，长篇后期术语和摘要是否顺畅未实测。
- **只测过 DeepSeek V4.1 Flash + WorkBuddy**，其他模型、其他 agent 未测。
- **都市、历史题材测得少，言情、悬疑没测过。**
- 复核是同一个模型查自己，和初稿错在同一处时查不出来。
- 每个新梗第一次出现时仍然要靠模型或人看出来（scan 只覆盖建书时能扫到的候选）。
- `scan` 测试时 agent 知道自己在被测误判，正常使用时可能没那么谨慎。
- README 的"目前的测试结果"一节还停在 v0.6 的数据，可以补上 scan 的结果。
- **日语版（v0.9.0）未经真模型测试**：
  - 长度检查的阈值（日语字数 / 中文字数 < 0.6 算太短，> 3.0 算太长）是估的，正常比例约 1.5，要用真译文校准。
  - 数字检查在日语一侧用"十分、一応、一度"等例外词表防误报，词表是手写的，可能还有漏网的误报。
  - "日语不用的字"按 cp932（日本常用字符集）判断：不在里面的汉字一律报错（如 剑、们、躲），另外手动列了几个在字符集里但现代日语不用的字（个、从、气……）。名字里确实没有日文字形的字用 `set keep_chars`。
  - 共享用语表（`slang/zh_internet_slang.tsv`）的建议译法和 avoid 列都是英文：日语书里任务文件会提示"如果是英文就用日语对应说法"，字面直译警告对共享表的词不起作用（书自己的 SLANG 行写日语就能起作用）。这是第 2 步要解决的。
  - 书自己的术语表、角色表沿用 `en` 列存日语译名（第 2 步再决定列名）。
  - 人名只保留汉字、不加读音；以后可以考虑 HTML/EPUB 的 `<ruby>` 注音。
- 速度：从零翻译约 45–50 秒/passage，每段输入 5–7k token；整本 270 万字的书需要几十小时机器时间。

`tests/scan_sample_*` 的标准答案由维护者保管，不放进仓库（仓库是公开的，被测的 agent 可能读到）。

## 7. 发布流程

- Claude 的 GitHub App 已对该仓库授权，可以直接 `git push origin main`。提交署名用 `LingHan-233 <LingHan-233@users.noreply.github.com>`。
- 推送 tag 时经常被代理断开，所以 **Release 和 tag 由维护者在 GitHub 网页上创建**（Releases → Draft a new release → 输入新 tag → Publish）。目前只建了 v0.6.1 的 Release。
- 每次发版：改 `VERSION`、`novel.py` 里的 `VERSION`、README 标题里的版本号；提交说明写清改了什么；另外打一个 zip 发给维护者（解压后就是仓库内容，不含 `.git`）。

## 8. 日语版（进行中）

维护者希望用户可以选择翻译成日语。评估：可行，难度中等，代码量约为英文版的三分之一。要点：

1. **目标语言参数**：`init --lang ja`（默认 en），任务文件加载 `lang/<lang>/` 下的风格说明和示例；`build` 的 EPUB/HTML 语言标签跟着变。
2. **检查要按语言分开，这是最大的工作量。**
   - "残留中文"检查：日语也用汉字，不能再按"有汉字就报错"。改为：段落没有假名（且不是很短的段）→ 疑似没翻；出现日语里不用的简体字（这、们、说、么、吗、呢、个、对、为、时、发、经、让 等）→ 报错。
   - 长度检查：按字符数比，不按英文单词数。
   - 翻译腔检查（STYLE_LINT）是英文专用的，日语版要么关闭，要么另写。
   - 数字检查：日语也用汉字数字，`cn_numbers` 可以复用在两侧。
   - 替代词字面直译检查：avoid 列要有日语版本。
3. **表格要支持多语言**：术语表、角色表、用语表目前只有一列英文。建议加 `ja` 列（或按语言分文件），没有 ja 列时回退到"让模型自己定并登记"。
4. **日语的优势**：修仙专名（宗门、境界、丹田、师兄）日语读者能直接读汉字，多数可以保留，只需转成日文字形（云→雲、师→師、门→門），人名保留汉字，可加读音。
5. **质量把关**：维护者大概率不懂日语。沿用"另一个模型修改 + 中文复述核对"的办法写 `lang/ja/` 的示例，最好请懂日语的人看一眼。示例全部原创。
6. **测试**：先用 `tests/sample_book.txt` 和 `tests/scan_sample_*.txt` 跑通，再在真书上试译几章，按第 1 节的测试循环出报告。

建议顺序：先做"语言参数 + 按语言分开的检查"（不影响英文版），再做表格多语言，最后写日语风格和示例。每一步都要确认英文版的流程没被改坏（用 `tests/workflow_run.py` 新旧版本各跑一遍再 diff）。

**进度（2026-11-06）**
- [x] 第 1 步：语言参数 + 按语言分开的检查（v0.9.0）。已做：`init --lang`、`set lang`、`set keep_chars`；残留中文（日语不用的字 / 中文专用字 / 整段没有假名）、按字数的长度检查、日语数字检查、日语否定词（抽查复核用）、日语注释和开场白检查；STYLE_LINT 只对英文；任务文件、复核文件、扫描任务、笔记提示里的语言名；EPUB/HTML 的语言标签、日文目录/章节名/声明、输出文件名 `-ja`。
- [x] 为了能实测，先写了 `lang/ja/` 的规则、人名、风格、仙侠和通用题材**草稿**（第 3 步的一部分）。待维护者用"另一个模型修改 + 中文复述核对"把关。
- [ ] 第 2 步：表格多语言（共享用语表加日语列，书的术语表列名）。
- [ ] 第 3 步：日语示例 `lang/ja/examples.md`（全部原创），都市、历史题材说明。
- [ ] 用真模型试译：示例书 + 真书几章，出报告。
