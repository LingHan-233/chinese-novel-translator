#!/usr/bin/env python3
"""
novel.py - workflow helper for the chinese-novel-translator skill.

The script does the bookkeeping so the model only has to translate:
it splits the book, builds one small self-contained task file per passage,
checks the model's output, keeps the glossary and character list up to date,
and assembles the finished book.

Standard library only. Python 3.8+.
Every command ends with a "NEXT:" line telling the agent what to do next.
"""

import argparse
import csv
import datetime
import hashlib
import html
import json
import os
import re
import sys
import uuid
import zipfile
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path
import xml.etree.ElementTree as ET

VERSION = "0.9.4"
SKILL_DIR = Path(__file__).resolve().parent.parent
HOME_NAME = "novel-translations"

CJK_RE = re.compile(r"[㐀-䶿一-鿿豈-﫿]")
CJK_RUN_RE = re.compile(r"[㐀-䶿一-鿿豈-﫿]+")
MARK_RE = re.compile(r"^\s*\[\[(T|P\d+)\]\]\s?(.*)$")
FENCE_RE = re.compile(r"^\s*```")
HEADING_RE = re.compile(
    r"^(第\s*[0-9０-９零〇一二两三四五六七八九十百千万]+\s*[章回节卷集部篇幕](?![分合门])"
    r"|序章|序言|楔子|引子|前言|尾声|终章|大结局|番外|后记|完本感言)"
)
VOLUME_RE = re.compile(r"^第\s*[0-9０-９零〇一二两三四五六七八九十百千万]+\s*[卷集部篇]")

GENRES = ["general", "xianxia", "urban", "historical"]
SETTABLE = {
    "trial": "bool",
    "polish": "bool",
    "review": "review",
    "genre": "str",
    "chunk_chars": "int",
    "title_en": "str",
    "author_en": "str",
    "lang": "lang",
    "keep_chars": "str",
}

META_PHRASES = [
    "here is the translation", "here's the translation", "translated text",
    "i hope this", "let me know", "as an ai", "translation:",
]
NOTE_PHRASES = ["translator's note", "translator’s note", "tl note", "tl:", "(note:", "[note:"]

# English habits that cheap models carry over from Chinese. Warnings only.
# (pattern, how many hits before warning, advice)
STYLE_LINT = [
    (r"\bcould(n't| not) help but\b", 1, "'couldn't help but' - usually drop it or say it plainly"),
    (r"\ba (trace|hint|sliver|touch) of\b", 2, "'a trace/hint of' repeated - say it directly"),
    (r"\bcorners? of (his|her|their|my) (mouth|lips)\b", 1, "'the corner of his mouth' - try 'a smile tugged at...' or just 'he smiled'"),
    (r"\b(instantly|in an instant|in that instant)\b", 2, "'instantly' repeated - let the action be sudden without it"),
    (r"\b(said|spoke|replied) (faintly|coldly|indifferently|lightly|flatly)\b", 1, "'said coldly/faintly' - let the line carry the tone, or use an action beat"),
    (r"\b(coldly|faintly) (snorted|smiled|said)\b", 1, "'coldly snorted' - 'He snorted.'"),
    (r"\b(his|her) heart (was|felt) (shocked|startled|alarmed)\b", 1, "'his heart was shocked' - 'he was startled'"),
    (r"\b(face|expression) (changed|was dim|grew dim)\b", 1, "'his face changed' - say how: paled, darkened, fell"),
    (r"\bthe door (behind him |behind her )?was knocked\b", 1, "'the door was knocked' - 'someone knocked at the door'"),
    (r"\bthe fact that\b", 2, "'the fact that' repeated - rephrase"),
    (r"\b(slightly|faintly|lightly) (raised|curved|curled|lifted)\b", 2, "stacked 'slightly/faintly' - cut the adverb"),
]

# Chinese phrases copied into Japanese kanji, found in real test runs. Warnings only.
JA_STYLE_LINT = [
    (r"眉毛まで燃え|火が眉毛|眉に火が", 1, "火烧眉毛 copied - Japanese says 尻に火がつく / 一刻を争う"),
    (r"頭に水", 1, "脑子进水 copied - Japanese says 頭がどうかしている / 正気か"),
    (r"一歩進んでは一歩見", 1, "走一步看一步 copied - Japanese says 出たとこ勝負 / 様子を見ながら進む"),
    (r"(泣く|泣き顔)より(も)?(醜い|ひどい)", 1, "比哭还难看 copied - try 今にも泣き出しそうな顔で / 引きつった笑み"),
    (r"平地に雷", 1, "平地惊雷 copied - Japanese says 青天の霹靂"),
    (r"AI(顔|換顔)", 1, "AI换脸 copied - Japanese says ディープフェイク"),
    (r"看家の", 1, "看家本领 copied - Japanese says 十八番 / とっておき"),
    (r"大功一件", 1, "立了大功 copied - Japanese says 大手柄"),
    (r"一張りの|一道の", 1, "a Chinese measure word copied (一张/一道) - Japanese: just 顔, or ひと筋の光"),
    (r"弁護士通知", 1, "律师函 copied - Japanese says 内容証明 / 弁護士からの警告書"),
    (r"心中一驚|心の中で一驚", 1, "心中一惊 copied - Japanese says ぎくりとした / はっとした"),
    (r"群魔乱舞|山呼海嘯|山が唸り海が嘯", 1, "a Chinese four-character phrase copied - say what it means in Japanese"),
    (r"天生の", 1, "天生 is not used alone in Japanese - 生まれながらの / 生まれつきの"),
    (r"余光で|余光に", 1, "余光 copied - Japanese says 目の端で / 視界の隅で"),
    (r"管事", 1, "管事 is not a Japanese word - 取りまとめ役 / 世話役"),
    (r"一抹の", 2, "「一抹の」 repeated - say it directly (かすかに笑った)"),
    (r"一(本|条)の(青|赤|黒|金|白)?龍", 1, "一条龙 copied - Japanese: just 青龍, or 一匹の龍 / 一体の龍"),
    (r"低声で", 1, "低声 copied - Japanese says 小声で / 声を落として"),
    (r"白い目を向け", 1, "白眼 - the Japanese phrase is 白い目で見る"),
    (r"瓜を切り|菜を刻むように", 1, "砍瓜切菜 copied - Japanese says 豆腐を切るように / 苦もなく"),
    (r"過江の", 1, "过江之鲫 copied - Japanese says 掃いて捨てるほど"),
    (r"心事を", 1, "心事 is not a Japanese word - 考え事 / 悩み"),
    (r"一博", 1, "一搏 copied - Japanese says 一か八か / 最後の賭け"),
    (r"血の糸", 1, "血丝 copied - Japanese says 目が血走る"),
    (r"淡々と(言|告|答)|冷たく(言|告|答)", 1, "淡淡道/冷冷道 copied - let the line carry the tone, or an action beat"),
]

# ----- numbers: compare what the English says with what the Chinese says
CN_DIGIT = {"零": 0, "〇": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6,
            "七": 7, "八": 8, "九": 9}
CN_IMPLIED = {"俩": 2, "双": 2, "对": 2, "仨": 3, "半": 2, "孪": 2, "两": 2}  # 俩人, 双剑, 一对, 仨, 半 (half)
CN_UNIT = {"十": 10, "百": 100, "千": 1000, "万": 10000, "亿": 100000000}
CN_NUM_RE = re.compile(r"[0-9０-９][0-9０-９,，.]*|[零〇一二两三四五六七八九十百千万亿]+")
EN_UNITS = {w: i for i, w in enumerate(
    "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen "
    "fifteen sixteen seventeen eighteen nineteen".split())}
EN_TENS = {w: (i + 2) * 10 for i, w in enumerate(
    "twenty thirty forty fifty sixty seventy eighty ninety".split())}
EN_ORD = {w: i + 1 for i, w in enumerate(
    "first _second_ third fourth fifth sixth seventh eighth ninth tenth eleventh twelfth "
    "thirteenth fourteenth fifteenth sixteenth seventeenth eighteenth nineteenth twentieth".split())}
EN_ORD.update({"thirtieth": 30, "fortieth": 40, "fiftieth": 50, "hundredth": 100,
               "thousandth": 1000})
EN_SCALE = {"hundred": 100, "thousand": 1000, "million": 1000000, "billion": 1000000000}


def cn_numbers(text):
    vals = set(v for ch, v in CN_IMPLIED.items() if ch in text)
    if re.search(r"[他她它你我]们|众人|大家|诸位|二人|两人", text):
        vals.add(2)  # "the two of them" for 他们 / 二人
    # 八成 = 80% = "eight in ten"
    for m in re.finditer(r"([一二两三四五六七八九十])成", text):
        n = CN_DIGIT.get(m.group(1), 10)
        vals.update({n, n * 10, 10})
    _number_runs(text, vals)
    return vals


def _number_runs(text, vals, lenient=True):
    """Add the value of every run of digits or Chinese number characters in text to vals.
    lenient (the Chinese side): each digit counts too, so 两三个 gives 2 and 3."""
    for run in CN_NUM_RE.findall(text):
        if run[0] in "0123456789０１２３４５６７８９":
            digits = run.translate(str.maketrans("０１２３４５６７８９", "0123456789"))
            digits = re.sub(r"[,，]", "", digits).rstrip(".")
            try:
                vals.add(int(float(digits)) if "." in digits else int(digits))
            except ValueError:
                pass
            continue
        total, section, num = 0, 0, 0
        for ch in run:
            if ch in CN_DIGIT:
                num = CN_DIGIT[ch]
                if lenient:
                    vals.add(num)  # 两三个 counts as 2 and 3
            else:
                unit = CN_UNIT[ch]
                if unit >= 10000:
                    total += (section + num) * unit
                    section = 0
                else:
                    section += (num or 1) * unit
                num = 0
        vals.add(total + section + num)


# A single number kanji only counts as a quantity when a counter or unit follows it (三回, 二人,
# 三メートル), so 二の腕 or 一石二鳥 are left out. Longer number words (三万, 九十九) always count,
# except before 数 (十数秒 = "a dozen seconds or so").
JA_COUNTER_RE = re.compile(
    r"(?:[つ人回度日年月歳才秒分時週晩夜代世歩本個匹頭羽枚杯冊台軒件品皿粒滴尺丈里斤両寸名位番階層段"
    r"章条句字円元銭倍割成部隊組撃発柱筋着足輪隻基張面戸家種色重門合刻里間ヶヵケかカ]|メートル|"
    r"キロ|センチ|パーセント|グラム|トン|ミリ|%|％)")
JA_NUM_RUN_RE = re.compile(r"[零〇一二三四五六七八九十百千万亿]+")


def ja_numbers(text):
    """Numbers a Japanese translation states: digits always; kanji numbers only when a counter
    follows (三回, 一万人), so words like 二の腕, 十数秒 or 十中八九 are not read as numbers."""
    vals = set()
    text = JA_NUM_IDIOMS.sub("、", text.replace("億", "亿"))
    digits = re.sub(r"[零〇一二三四五六七八九十百千万亿]", "、", text)
    _number_runs(digits, vals, lenient=False)
    for m in JA_NUM_RUN_RE.finditer(text):
        rest = text[m.end():]
        if rest.startswith("数"):  # 十数秒, 百数十 = "a dozen or so": not an exact number
            continue
        if len(m.group(0)) == 1 and not JA_COUNTER_RE.match(rest):
            continue
        _number_runs(m.group(0), vals, lenient=False)
    return vals


def en_numbers(text):
    vals = set()
    for m in re.finditer(r"\d[\d,]*(?:\.\d+)?", text):
        try:
            vals.add(int(float(m.group(0).replace(",", ""))))
        except ValueError:
            pass
    words = re.findall(r"[a-z]+", text.lower().replace("-", " "))
    total, current, active = 0, 0, False

    def flush():
        if active:
            vals.add(total + current)

    skip_next = [False]
    for i, w in enumerate(words):
        nxt_w = words[i + 1] if i + 1 < len(words) else ""
        if skip_next[0]:
            skip_next[0] = False
            if w in ("a",) and nxt_w in EN_SCALE:
                skip_next[0] = True
            continue
        if w in EN_UNITS or w in EN_TENS:
            current += EN_UNITS.get(w, 0) + EN_TENS.get(w, 0)
            active = True
        elif w in EN_ORD:
            current += EN_ORD[w]
            active = True
            flush()
            total, current, active = 0, 0, False
        elif w in EN_SCALE:
            if w == "hundred":
                current = (current or 1) * 100
            else:
                total += (current or 1) * EN_SCALE[w]
                current = 0
            active = True
        elif w == "in" and nxt_w in ("ten", "a", "hundred", "thousand", "million") and active:
            flush()  # "eight in ten", "one in a hundred": a ratio, the second number is not a quantity
            total, current, active = 0, 0, False
            skip_next[0] = True
            continue
        elif w == "a" and nxt_w in EN_SCALE:
            current, active = 1, True
        elif w == "and" and active and (nxt_w in EN_UNITS or nxt_w in EN_TENS):
            continue
        else:
            flush()
            total, current, active = 0, 0, False
    flush()
    return vals


ZH_NEG_RE = re.compile(r"[不没未别无非莫勿]")
EN_NEG_RE = re.compile(r"\b(not|no|never|nothing|nobody|none|neither|nor|cannot|without|nowhere)\b|n't",
                       re.I)


def negation_mismatch(zh, en, lang="en"):
    """True when only one side has a negation word. Noisy, so it only steers the spot review."""
    neg = JA_NEG_RE if lang == "ja" else EN_NEG_RE
    return bool(ZH_NEG_RE.search(zh)) != bool(neg.search(en or ""))


def number_mismatch(zh, en, lang="en"):
    """Numbers the translation states that the Chinese does not (1 is ignored: 'a', 'once', 'no one')."""
    zh_vals = cn_numbers(zh)
    found = ja_numbers(en or "") if lang == "ja" else en_numbers(en)
    extra = sorted(v for v in found - zh_vals if v not in (0, 1))
    return extra


STOP_CHARS = set(
    "的了是在我你他她它们这那不就也都着过吗呢吧啊么和与而又很太还没已被把让给对从到向"
    "一个有说道上下来去出看想要会能得地之其此所为以于什么怎样些自己好人中大小里"
)


# ----------------------------------------------------------- target languages
# The book's target language is book.json "target_lang" (set with `init --lang`).
# English is the default and behaves exactly as before; everything language-specific
# for other languages is looked up here or in lang/<code>/.

LANGS = {
    "en": {"name": "English", "label": "EN"},
    "ja": {"name": "Japanese", "label": "JA"},
}

KANA_RE = re.compile(r"[ぁ-ゟ゠-ヿㇰ-ㇿｦ-ﾟ]")
# Chinese-only characters that are also in the Japanese (cp932) character set but are not
# used in modern Japanese (个 for 個, 从 for 従, 气 for 気 ...).
ZH_ONLY_IN_JIS = set("个从无它气听价决况坏愿档梦泪犹盖粮网赶嘛咋")
# Words that only Chinese grammar uses: if they show up, the sentence was not translated.
ZH_GRAMMAR = set("这们说么吗个对为时发经让过还进从她它您吧哪咱啥咋给样么")
# 2010 jōyō forms that are not in cp932 but are correct Japanese.
JA_EXTRA_OK = set("𠮟塡剝頰")
JA_NOTE_PHRASES = ["訳注", "訳者注", "（注", "(注", "［注", "[注", "注：", "注:"]
JA_META_PHRASES = ["以下は", "以下が", "翻訳：", "翻訳:", "訳文：", "訳文:", "日本語訳"]
JA_NEG_RE = re.compile(r"ない|なかっ|なく|ません|ず[、。にとも]|ぬ|まい|無|不|非|未|なし|いや|いいえ")
# Japanese words that contain number kanji without meaning a number (十分 = enough).
JA_NUM_IDIOMS = re.compile(
    r"十分|万が一|万一|一応|一体|一緒|一瞬|一斉|一気|一番|一層|一旦|一向|唯一|統一|同一|"
    r"百も承知|千切|八つ当たり|四方八方|二度と|一度|一人|一つ|一言|一同|一方|一部|一切|万全|"
    r"万事|万能|千載一遇|一石二鳥|三日月|七夕|八百屋|十八番|五分五分|九死に一生|"
    r"万歳|千差万別|一目|一息|一声|一歩|一礼|一行|一角|一面|一族|一門|一派|"
    r"十中八九|九分九厘|三枚肉|四六時中|七転八倒|四苦八苦|八方美人|三日坊主|一か八か|一挙一動|"
    r"十人十色|百発百中|一触即発|二枚目|三枚目|一枚岩|唯一無二|一長一短|一進一退|千変万化|"
    r"百戦錬磨|八つ裂き|五臓六腑|三拍子|七色|一心不乱|一目散|三々五々|再三|二の足|一石|"
    r"一刻|一晩|一生|一時|一応|一筋|一種|一味|一流|一家|一般|一致|一変|一転|一新")


# Chinese-only words written with characters Japanese also has (十几秒 = 十数秒).
ZH_ONLY_WORDS = re.compile(r"[十百千万]几|几[十百千万个天年次人]|几乎|好几|没有|什么|怎么|为什么")


def lang_info(code):
    return LANGS.get(code or "en", LANGS["en"])


def is_japanese_char(ch):
    """True if a CJK character belongs to ordinary Japanese (it is in the cp932 set)."""
    if ch in JA_EXTRA_OK:
        return True
    if ch in ZH_ONLY_IN_JIS:
        return False
    try:
        ch.encode("cp932")
        return True
    except UnicodeEncodeError:
        return False


def leftover_chinese(text, lang="en", keep=""):
    """Chinese left in a translation: (error message or "", list of the characters).
    English: any CJK character. Japanese: kanji are fine, but characters Japanese does not
    use (simplified forms like 剑, 门, or Chinese-only words like 这, 们) are not."""
    if lang == "en":
        found = CJK_RUN_RE.findall(text or "")
        return ("still contains Chinese: " + " ".join(found[:5])) if found else "", found
    bad = []
    for ch in CJK_RE.findall(text or ""):
        if ch not in keep and not is_japanese_char(ch) and ch not in bad:
            bad.append(ch)
    words = ZH_ONLY_WORDS.findall(text or "")
    if words and not bad:
        return ("still contains Chinese words: %s. Write them in Japanese (十几秒 → 十数秒, "
                "几天 → 数日)." % " ".join(words[:5])), words
    if not bad:
        return "", bad
    grammar = [c for c in bad if c in ZH_GRAMMAR]
    if grammar:
        return ("still contains Chinese (Chinese-only words: %s): translate the whole "
                "sentence into Japanese." % " ".join(grammar[:5])), bad
    return ("has characters that Japanese does not use: %s. Use the Japanese form "
            "(剑→剣, 门→門, 灵→霊, 苏→蘇, 刘→劉) or write the word in kana or as another Japanese "
            "word. Only if it is part of a name and has no Japanese form, run `%s set keep_chars %s`."
            % (" ".join(bad[:8]), py_cmd(), "".join(bad[:8]))), bad


def text_size(text, lang="en"):
    """Length of a translation for the too-short/too-long check:
    English counts words, Japanese counts characters (kana, kanji, letters, digits)."""
    if lang == "en":
        return word_count(text)
    return len(re.findall(r"[\wぁ-ゟ゠-ヿ㐀-䶿一-鿿豈-﫿々〆ヶ]", text or ""))


# too short / too long, in "translation size per Chinese character". English: words.
# Japanese: characters (a Chinese passage usually becomes about 1.3-1.8 times as many).
LENGTH_LIMITS = {"en": (0.25, 1.7), "ja": (0.6, 3.0)}
# paragraphs shorter than this (Chinese characters) are not length-checked
LENGTH_MIN_ZH = {"en": 30, "ja": 15}
# below 30 Chinese characters a natural Japanese line can be much shorter (这话说给谁听呢！ →
# 誰に言っているんだ！ = 0.56), so the "too short" limit is looser there
SHORT_PARA_LIMIT = {"ja": 0.4}


# ----------------------------------------------------------------- utilities

WORK_DISPLAY = ["work"]  # set to the real work-folder path once a book is loaded
_WORK_RE = re.compile(r"(?<![\w/\\])work/")


def show_paths(msg):
    """Replace the short 'work/' prefix with the real path the agent should use."""
    return _WORK_RE.sub(WORK_DISPLAY[0].replace("\\", "/") + "/", msg)


def display_path(p):
    try:
        return str(Path(p).resolve().relative_to(Path.cwd().resolve())).replace("\\", "/")
    except ValueError:
        return str(Path(p).resolve()).replace("\\", "/")


def out(msg=""):
    print(show_paths(msg))


def nxt(msg):
    print("")
    print("NEXT: " + show_paths(msg))


def fail(msg, next_msg=None):
    print("ERROR: " + show_paths(msg))
    if next_msg:
        nxt(next_msg)
    sys.exit(1)


def py_cmd():
    """How the agent should call this script (relative path if possible)."""
    script = Path(__file__).resolve()
    try:
        rel = script.relative_to(Path.cwd())
        return "python " + str(rel)
    except ValueError:
        return 'python "' + str(script) + '"'


def has_cjk(s):
    return bool(CJK_RE.search(s or ""))


def cjk_count(s):
    return len(CJK_RE.findall(s or ""))


def word_count(s):
    return len(re.findall(r"[A-Za-z0-9']+", s or ""))


def read_text_file(path):
    raw = Path(path).read_bytes()
    if raw.startswith(b"\xff\xfe") or raw.startswith(b"\xfe\xff"):
        return raw.decode("utf-16")
    for enc in ("utf-8-sig", "gb18030", "big5"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def clean_para(s):
    s = s.replace("　", " ").replace("\xa0", " ").replace("﻿", "")
    s = re.sub(r"[ \t]+", " ", s)
    return s.strip()


def slugify(name):
    s = re.sub(r"[^\w一-鿿-]+", "-", name).strip("-")
    return s or "book"


def read_tsv(path):
    """Read a TSV with a header row. Lines starting with # are comments."""
    rows = []
    p = Path(path)
    if not p.exists():
        return rows
    lines = [ln for ln in p.read_text(encoding="utf-8").splitlines()
             if ln.strip() and not ln.lstrip().startswith("#")]
    if not lines:
        return rows
    reader = csv.reader(lines, delimiter="\t", quoting=csv.QUOTE_NONE)
    header = None
    for row in reader:
        if header is None:
            header = [h.strip() for h in row]
            continue
        row = row + [""] * (len(header) - len(row))
        rows.append({header[i]: row[i].strip() for i in range(len(header))})
    return rows


def write_tsv(path, header, rows, comments=None):
    lines = []
    for c in comments or []:
        lines.append("# " + c)
    lines.append("\t".join(header))
    for r in rows:
        lines.append("\t".join(str(r.get(h, "")).replace("\t", " ").replace("\n", " ")
                               for h in header))
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")


def variants(zh, aliases=""):
    """All Chinese forms of a name: 'A/B' plus an aliases field 'C/D'."""
    vs = []
    for part in (zh or "").split("/") + (aliases or "").split("/"):
        part = part.strip()
        if part and part not in vs:
            vs.append(part)
    return vs


# ------------------------------------------------------------- book import

class _EpubText(HTMLParser):
    BLOCK = {"p", "div", "br", "li", "blockquote", "section", "tr", "h1", "h2",
             "h3", "h4", "h5", "h6", "article", "dd", "dt", "pre"}
    HEAD = {"h1", "h2", "h3", "h4", "h5", "h6"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.items = []  # (kind, text)
        self.buf = []
        self.skip = 0
        self.in_head = 0

    def _flush(self):
        text = clean_para("".join(self.buf))
        self.buf = []
        if text:
            self.items.append(("h" if self.in_head else "p", text))

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "head", "title"):
            self.skip += 1
        if tag in self.BLOCK:
            self._flush()
        if tag in self.HEAD:
            self.in_head += 1

    def handle_endtag(self, tag):
        if tag in self.BLOCK:
            self._flush()
        if tag in self.HEAD and self.in_head:
            self.in_head -= 1
        if tag in ("script", "style", "head", "title") and self.skip:
            self.skip -= 1

    def handle_data(self, data):
        if not self.skip:
            self.buf.append(data)

    def close(self):
        super().close()
        self._flush()


def _local(tag):
    return tag.rsplit("}", 1)[-1]


def read_epub(path):
    z = zipfile.ZipFile(path)
    container = z.read("META-INF/container.xml").decode("utf-8", errors="replace")
    m = re.search(r'full-path\s*=\s*["\']([^"\']+)["\']', container)
    if not m:
        fail("This EPUB has no package file (container.xml is broken).")
    opf_path = m.group(1)
    base = opf_path.rsplit("/", 1)[0] + "/" if "/" in opf_path else ""
    root = ET.fromstring(z.read(opf_path))
    title = ""
    manifest = {}
    spine = []
    for el in root.iter():
        name = _local(el.tag)
        if name == "title" and not title and (el.text or "").strip():
            title = el.text.strip()
        elif name == "item":
            manifest[el.get("id")] = (el.get("href"), el.get("properties") or "")
        elif name == "itemref":
            spine.append(el.get("idref"))
    chapters = []
    skipped = []
    for idref in spine:
        href, props = manifest.get(idref, (None, ""))
        if not href:
            continue
        if "nav" in props.split():
            skipped.append(href)
            continue
        full = base + href.split("#")[0]
        try:
            data = z.read(full).decode("utf-8", errors="replace")
        except KeyError:
            continue
        parser = _EpubText()
        parser.feed(data)
        parser.close()
        items = parser.items
        total = sum(len(t) for _, t in items)
        if total < 30:
            continue
        ch_title = ""
        body = []
        for kind, text in items:
            if kind == "h" and not ch_title:
                ch_title = text
            else:
                body.append(text)
        if not ch_title and body and len(body[0]) <= 40 and HEADING_RE.match(body[0]):
            ch_title = body.pop(0)
        if not ch_title and body and len(body[0]) <= 10 and TOC_TITLE_RE.match(body[0]):
            ch_title = body.pop(0)
        if looks_like_toc(ch_title, body):
            skipped.append(ch_title or href)
            continue
        if body:
            chapters.append({"title": ch_title, "paras": body})
    return title, chapters, skipped


def split_txt(text):
    lines = [clean_para(ln) for ln in text.splitlines()]
    lines = [ln for ln in lines if ln]
    chapters = []
    current = {"title": "", "paras": []}
    found = 0
    for ln in lines:
        if len(ln) <= 50 and HEADING_RE.match(ln):
            found += 1
            if current["paras"]:
                chapters.append(current)
            elif current["title"] and not VOLUME_RE.match(current["title"]):
                # heading with no body: keep it as a paragraph of the next chapter
                pass
            current = {"title": ln, "paras": []}
        else:
            current["paras"].append(ln)
    if current["paras"]:
        chapters.append(current)
    if found == 0:
        # no chapter headings: cut into pseudo-chapters of ~6000 characters
        chapters = []
        cur = {"title": "", "paras": []}
        size = 0
        for ln in lines:
            cur["paras"].append(ln)
            size += len(ln)
            if size >= 6000:
                chapters.append(cur)
                cur = {"title": "", "paras": []}
                size = 0
        if cur["paras"]:
            chapters.append(cur)
    # a text block before the first heading (书名, 作者, 简介...) is front matter
    if chapters and not chapters[0]["title"] and found:
        chapters[0]["front"] = True
    return mark_front(chapters)


TOC_TITLE_RE = re.compile(r"^\s*(目\s*录|目\s*錄|contents|table of contents)\s*$", re.I)


def looks_like_toc(title, paras):
    """A table of contents: titled 目录, or mostly a long list of chapter headings."""
    if TOC_TITLE_RE.match(title or ""):
        return True
    if len(paras) >= 10:
        heads = sum(1 for p in paras if len(p) <= 50 and HEADING_RE.match(p))
        return heads >= 0.6 * len(paras)
    return False


def mark_front(chapters):
    """Everything before the first real chapter heading (书名/简介/版权...) is front matter."""
    for i, ch in enumerate(chapters):
        if ch.get("title") and HEADING_RE.match(ch["title"]):
            if 0 < i <= 6:
                for c in chapters[:i]:
                    c["front"] = True
            return chapters
    return chapters


def chunk_paras(paras, limit):
    chunks = []
    cur = []
    size = 0
    for p in paras:
        if cur and size + len(p) > limit:
            chunks.append(cur)
            cur = []
            size = 0
        cur.append(p)
        size += len(p)
    if cur:
        chunks.append(cur)
    # avoid a tiny last chunk: merge it into the previous one
    if len(chunks) > 1 and sum(len(p) for p in chunks[-1]) < limit * 0.25:
        tail = chunks.pop()
        chunks[-1].extend(tail)
    return chunks


# ---------------------------------------------------------------- workspace

class Book:
    def __init__(self, ws):
        self.ws = Path(ws)
        self.cfg_path = self.ws / "book.json"
        self.cfg = json.loads(self.cfg_path.read_text(encoding="utf-8"))
        WORK_DISPLAY[0] = display_path(self.ws / "work")

    # paths
    @property
    def bible(self):
        return self.ws / "bible"

    @property
    def work(self):
        return self.ws / "work"

    def src_path(self, cid):
        return self.ws / "source" / (cid + ".json")

    def tr_path(self, cid):
        return self.ws / "translated" / (cid + ".md")

    def save(self):
        self.cfg_path.write_text(json.dumps(self.cfg, ensure_ascii=False, indent=1),
                                 encoding="utf-8")

    # data
    def chunk_ids(self):
        ids = []
        for ch in self.cfg["chapters"]:
            if not ch.get("skip"):
                ids.extend(ch["chunks"])
        return ids

    def source(self, cid):
        return json.loads(self.src_path(cid).read_text(encoding="utf-8"))

    def done(self):
        return set(self.cfg.get("done", []))

    def glossary(self):
        return read_tsv(self.bible / "glossary.tsv")

    def characters(self):
        return read_tsv(self.bible / "characters.tsv")

    def slang_off(self):
        p = self.bible / "slang_off.txt"
        if not p.exists():
            return set()
        return {ln.strip() for ln in p.read_text(encoding="utf-8").splitlines()
                if ln.strip() and not ln.startswith("#")}

    def slang(self):
        """Shared slang table plus this book's own (bible/slang_extra.tsv). The book wins.
        Terms listed in bible/slang_off.txt are dropped."""
        off = self.slang_off()
        merged = {}
        lang = self.lang
        for r in read_tsv(SKILL_DIR / "slang" / "zh_internet_slang.tsv"):
            if lang != "en":  # the shared table has default_<lang> / avoid_<lang> columns
                own = r.get("default_" + lang, "")
                r = dict(r, default_en=own or (r.get("default_en", "") + " (English hint)"),
                         avoid=r.get("avoid_" + lang, ""))
            merged[r.get("term", "")] = r
        for r in read_tsv(self.bible / "slang_extra.tsv"):
            merged[r.get("term", "")] = dict(r, book="yes")
        return [r for t, r in merged.items() if t and t not in off]

    def summaries(self):
        return read_tsv(self.ws / "summaries.tsv")

    # target language
    @property
    def lang(self):
        return self.cfg.get("target_lang") or "en"

    @property
    def lname(self):
        return lang_info(self.lang)["name"]

    def keep_chars(self):
        """Characters a Japanese translation may keep although Japanese does not use them
        (a name character with no Japanese form). Set with `set keep_chars`."""
        return self.cfg.get("keep_chars") or ""


def workspace_from_args(args):
    if getattr(args, "workspace", None):
        ws = Path(args.workspace)
    else:
        pointer = Path.cwd() / HOME_NAME / "CURRENT"
        if not pointer.exists():
            fail("No book is open in this folder.",
                 py_cmd() + " init <path-to-book.txt-or-.epub>")
        ws = Path.cwd() / HOME_NAME / pointer.read_text(encoding="utf-8").strip()
    if not (ws / "book.json").exists():
        fail("Workspace not found: " + str(ws),
             py_cmd() + " init <path-to-book.txt-or-.epub>")
    return Book(ws)


# ------------------------------------------------------------------ init

def cmd_init(args):
    src = Path(args.book)
    if not src.exists():
        fail("File not found: " + str(src))
    if args.genre not in GENRES:
        fail("Unknown genre. Use one of: " + ", ".join(GENRES))
    if args.lang not in LANGS:
        fail("Unknown target language. Use one of: " + ", ".join(LANGS))
    skipped = []
    if src.suffix.lower() == ".epub":
        title, chapters, skipped = read_epub(src)
        chapters = mark_front(chapters)
    else:
        title = ""
        chapters = split_txt(read_text_file(src))
    if not chapters:
        fail("Could not find any text in " + str(src))
    title = title or src.stem

    home = Path(args.root or Path.cwd()) / HOME_NAME
    slug = slugify(args.name or src.stem)
    ws = home / slug
    if (ws / "book.json").exists() and not args.force:
        fail("This book was already set up in " + str(ws) + ". Add --force to start over "
             "(this deletes progress).", py_cmd() + " status")
    for sub in ("source", "translated", "bible", "work", "output"):
        (ws / sub).mkdir(parents=True, exist_ok=True)
    WORK_DISPLAY[0] = display_path(ws / "work")

    cfg_chapters = []
    n = 0
    for i, ch in enumerate(chapters, 1):
        ids = []
        parts = chunk_paras(ch["paras"], args.chunk_chars)
        for j, paras in enumerate(parts, 1):
            n += 1
            cid = "%04d" % n
            ids.append(cid)
            (ws / "source" / (cid + ".json")).write_text(json.dumps({
                "chapter": i, "part": j, "parts": len(parts),
                "title": ch["title"], "paras": paras, "front": bool(ch.get("front")),
            }, ensure_ascii=False, indent=1), encoding="utf-8")
        entry = {"n": i, "title": ch["title"], "chunks": ids}
        if ch.get("front"):
            entry["front"] = True
        cfg_chapters.append(entry)

    cfg = {
        "version": 1,
        "title": title,
        "title_en": "",
        "author_en": "",
        "source_file": str(src.resolve()),
        "genre": args.genre,
        "target_lang": args.lang,
        "chunk_chars": args.chunk_chars,
        "trial": not args.no_trial,
        "polish": False,
        "review": args.review,
        "chapters": cfg_chapters,
        "done": [],
        "current": None,
        "stage": None,
        "created": datetime.date.today().isoformat(),
    }
    (ws / "book.json").write_text(json.dumps(cfg, ensure_ascii=False, indent=1),
                                  encoding="utf-8")
    tpl = SKILL_DIR / "templates"
    for name in ("glossary.tsv", "characters.tsv", "synopsis.md"):
        target = ws / "bible" / name
        if not target.exists() or args.force:
            target.write_text((tpl / name).read_text(encoding="utf-8"), encoding="utf-8")
    if args.force:
        for f in list((ws / "translated").glob("*.md")):
            f.unlink()
        s = ws / "summaries.tsv"
        if s.exists():
            s.unlink()
    (home / "CURRENT").write_text(slug, encoding="utf-8")

    total_chars = sum(len(p) for ch in chapters for p in ch["paras"])
    out("Book set up: " + title)
    out("Workspace: " + str(ws))
    out("Chapters: %d   Passages: %d   Text length: %d characters" %
        (len(chapters), n, total_chars))
    out("Genre module: " + args.genre + "   Trial mode: " + ("on" if cfg["trial"] else "off")
        + "   Review pass: " + args.review)
    out("Translating into: %s (%s)" % (lang_info(args.lang)["name"], args.lang))
    if skipped:
        out("Left out (table of contents / navigation): " + ", ".join(skipped[:5]))
    out("First chapters found:")
    for ch in cfg_chapters[:6]:
        label = ((ch["title"] + " " if ch["title"] else "") + "(front matter)") if ch.get("front") \
            else (ch["title"] or "(no title)")
        out("  %d. %s (%d passages)" % (ch["n"], label, len(ch["chunks"])))
    out("If something here is not part of the story (an index, ads, author notes you don't want), "
        "leave it out with `" + py_cmd() + " skip <number>`.")
    if len(chapters) == 1 and total_chars > 20000:
        out("WARNING: only one chapter was found in a long text. Chapter headings may use an "
            "unusual format; the book will still work, but chapter titles will be missing.")
    nxt("Build the story bible (SKILL.md step 2): run `" + py_cmd() + " candidates` and read "
        "the beginning of the book.")


# ------------------------------------------------------------- candidates

def cmd_candidates(args):
    book = workspace_from_args(args)
    chapters = book.cfg["chapters"][: args.chapters]
    text_parts = []
    for ch in chapters:
        for cid in ch["chunks"]:
            text_parts.extend(book.source(cid)["paras"])
    text = "\n".join(text_parts)
    known = set()
    for r in book.glossary():
        known.update(variants(r.get("zh")))
    for r in book.characters():
        known.update(variants(r.get("zh"), r.get("aliases")))

    counts = Counter()
    for run in CJK_RUN_RE.findall(text):
        for n in (2, 3, 4):
            for i in range(len(run) - n + 1):
                g = run[i:i + n]
                if g[0] in STOP_CHARS or g[-1] in STOP_CHARS:
                    continue
                if sum(1 for c in g if c in STOP_CHARS) > n // 2:
                    continue
                counts[g] += 1
    min_count = max(3, args.min_count)
    cand = {g: c for g, c in counts.items() if c >= min_count}
    # drop fragments that mostly occur inside a longer candidate
    for g in sorted(cand, key=len):
        for longer, lc in cand.items():
            if len(longer) > len(g) and g in longer and lc >= cand[g] * 0.7:
                cand[g] = 0
                break
    ranked = sorted(((c, g) for g, c in cand.items() if c and g not in known), reverse=True)
    ranked = ranked[: args.top]
    out("Frequent words in the first %d chapter(s) that are not in the bible yet." % len(chapters))
    out("These are only guesses: most are ordinary words. Pick out names of people, places,")
    out("sects, techniques, items, titles and recurring special terms.")
    out("")
    line = []
    for c, g in ranked:
        line.append("%s(%d)" % (g, c))
        if len(line) == 8:
            out("  " + "  ".join(line))
            line = []
    if line:
        out("  " + "  ".join(line))
    if not ranked:
        out("  (nothing new found)")
    scan_stand_ins(book, known)
    nxt("Write the real names and terms into a file such as work/bible_notes.md using lines like\n"
        "  CHAR: 林凡 | Lin Fan | male | protagonist, calls himself 老子 when angry | 小凡/林哥\n"
        "  TERM: 青云宗 | Azure Cloud Sect | sect | \n"
        "  SLANG: 牛至 | stand-in for 牛子 (penis) | deadpan | his johnson | never literal | oregano\n"
        "then run `" + py_cmd() + " add work/bible_notes.md`. Gender: write it only when the text "
        "makes it clear (他/她, 师兄/师姐, 公子/姑娘); otherwise write unknown - never guess from "
        "the name. Ask the user to check genders and fill bible/synopsis.md if they know the "
        "book. Then run `" + py_cmd() + " scan` to let the model judge the suspicious words "
        "(stand-ins), and after that `" + py_cmd() + " next`.")


COMMON_DOUBLED = set(
    "常渐慢刚妈爸哥姐弟妹爷奶叔舅姥婆公伯姑宝星往偏天年人处个默轻静紧微悄好久时纷匆连稍隐淡冷深狠"
    "重缓远早统仅白生足呵哈嘿嘻嗯啊哼呜嘤咚轰哒滴啪砰谢看想试说走等种样句声步层道条片点丝阵团家事区"
    "堂赫茫滚腾熊蒙楚翩姗涛哗呼嗡叮咕噗嘎嘶哦唉喂嗷呃咳咦哇哎嗒噼滋扑沙簌汪喵蹭飕刷咔吱叽咯嘀唰"
    "怔愣暗明高低大小多少快真恰频频屡屡源源恰恰苦苦乖乖实实明明暗暗来去上下左右前后东西南北口心眼手"
    "一死笑整问了平齐满悠面麻短密长隆喃翼老瑟哆嗦絮叨唠扭歪弯斑点亮闪灼熠皑袅潺汩淙铮锵叮当"
    "朦胧迷懵呆傻乐美甜香暖凉温柔软硬粗细厚薄胖瘦鼓圆尖方直空晃摇荡飘漂摆抖颤蹦跳拍敲踢挠捏揉")


# a doubled word that is really "...宗" + "宗主" (星岚宗宗主), not a word of its own
SEAM_NEXT = set("主长老首众弟徒规内外")
# characters that, right before a word, suggest it is used as a noun: 的金金, 那根牛至, 把金金
NOUN_BEFORE = set("的个根条只颗块把对两几些这那他她它我你其被将拿摸抓掏露")
FUNCTION_BEFORE = set("的了是在着地得不也都就又还很太把被给让和与他她它我你这那一")


def book_text(book):
    parts = []
    for ch in book.cfg["chapters"]:
        if ch.get("skip"):
            continue
        for cid in ch["chunks"]:
            parts.extend(book.source(cid)["paras"])
    return "\n".join(parts)


def snippet(text, word, width=8):
    i = text.find(word)
    if i < 0:
        return ""
    a, b = max(0, i - width), min(len(text), i + len(word) + width)
    return "..." + text[a:b].replace("\n", " ") + "..."


def doubled_candidates(text, exclude, limit=30):
    """Doubled words that look like nouns (金金, 牛牛), skipping name seams (宗宗主), idiom
    pieces (小心翼翼, 老老实实) and very common words. Ranked by how noun-like they are."""
    occ = {}
    for m in re.finditer(r"([\u4e00-\u9fff])\1", text):
        w, c = m.group(0), m.group(1)
        if c in COMMON_DOUBLED or w in exclude:
            continue
        before = text[m.start() - 1] if m.start() > 0 else ""
        after = text[m.end()] if m.end() < len(text) else ""
        after2 = text[m.end():m.end() + 2]
        occ.setdefault(w, []).append((before, after, after2))
    result = []
    for w, hits in occ.items():
        n = len(hits)
        if n < 3:
            continue
        if sum(1 for _, a, _ in hits if a in SEAM_NEXT) > n / 2:
            continue  # 宗宗主, 庄庄主
        if sum(1 for _, _, a2 in hits if len(a2) == 2 and a2[0] == a2[1]) > n / 2:
            continue  # 老老实实
        befores = Counter(b for b, _, _ in hits)
        top_b, top_n = befores.most_common(1)[0]
        if top_n > n * 0.8 and top_b and top_b not in FUNCTION_BEFORE and n >= 5:
            continue  # 小心翼翼: always the same character in front
        noun = sum(1 for b, _, _ in hits if b in NOUN_BEFORE) / float(n)
        if n > 150:
            noun *= 0.5  # very frequent words are almost never in-jokes
        result.append((round(noun, 2), n, w))
    result.sort(key=lambda r: (-r[0], -r[1]))
    return [(w, n, noun) for noun, n, w in result[:limit]]


def scan_stand_ins(book, known):
    """Point out doubled words (金金, 牛牛) and shared stand-in words anywhere in the book."""
    text = book_text(book)
    slang_terms = {r.get("term") for r in book.slang()}
    doubled = doubled_candidates(text, known | slang_terms)
    stand_ins = []
    for r in book.slang():
        if "stand-in" in (r.get("tone") or "") and r.get("term") in text:
            stand_ins.append((text.count(r["term"]), r["term"]))
    stand_ins.sort(reverse=True)
    out("")
    out("Doubled words that look like nouns (金金, 牛牛 style), whole book, most noun-like first. "
        "Web novels often use a cute doubled word as a stand-in for a rude one. Read the "
        "example; most will be harmless:")
    if doubled:
        for w, n, _ in doubled:
            out("  %s(%d)  %s" % (w, n, snippet(text, w)))
    else:
        out("  (none)")
    if stand_ins:
        out("Stand-in words from the shared slang table that appear in this book. Check the "
            "example: if a word is always meant literally in this book (小兄弟 = a young man), "
            "add a line `NOSLANG: 小兄弟` to your notes so it stops being flagged:")
        for c, w in stand_ins:
            out("  %s(%d)  %s" % (w, c, snippet(text, w)))


# ---------------------------------------------------------- notes merging

def parse_notes(text, lang="en", keep=""):
    summary = []
    terms = []
    chars = []
    problems = []
    for raw in text.splitlines():
        line = raw.strip().lstrip("-*").strip()
        if not line:
            continue
        up = line.upper()
        if up.startswith("SUMMARY:"):
            summary.append(line.split(":", 1)[1].strip())
        elif up.startswith("TERM:"):
            f = [x.strip() for x in line.split(":", 1)[1].split("|")]
            if len(f) < 2 or not f[0] or not f[1]:
                problems.append("Bad TERM line (need at least 中文 | English): " + line)
                continue
            f += [""] * (4 - len(f))
            terms.append({"zh": f[0], "en": f[1], "type": f[2], "note": f[3]})
        elif up.startswith("CHAR:"):
            f = [x.strip() for x in line.split(":", 1)[1].split("|")]
            if len(f) < 3 or not f[0] or not f[1]:
                problems.append("Bad CHAR line (need 中文 | English | gender): " + line)
                continue
            f += [""] * (5 - len(f))
            chars.append({"zh": f[0], "en": f[1], "gender": f[2], "note": f[3], "aliases": f[4]})
    good_terms, good_chars = [], []
    for rows, good in ((terms, good_terms), (chars, good_chars)):
        for row in rows:
            ok = True
            if not has_cjk(row["zh"]):
                problems.append("The first field must be the Chinese original: " + row["zh"])
                ok = False
            if lang == "en" and has_cjk(row["en"]):
                problems.append("The English field still contains Chinese: " + row["en"])
                ok = False
            if lang != "en":
                problem, _ = leftover_chinese(row["en"], lang, keep)
                if problem:
                    problems.append("The %s field of %s %s" % (lang_info(lang)["name"], row["zh"],
                                                              problem))
                    ok = False
            if ok or lang == "en":
                good.append(row)
    return " ".join(summary).strip(), good_terms, good_chars, problems


SLANG_HEADER = ["term", "meaning", "tone", "default_en", "strategy", "avoid"]


def parse_slang(text):
    """SLANG: 中文 | meaning | tone | suggested English | how to handle | literal English to avoid"""
    rows, problems = [], []
    for raw in text.splitlines():
        line = raw.strip().lstrip("-*").strip()
        if not line.upper().startswith("SLANG:"):
            continue
        f = [x.strip() for x in line.split(":", 1)[1].split("|")]
        if len(f) < 4 or not f[0] or not f[1] or not f[3]:
            problems.append("Bad SLANG line (need 中文 | meaning | tone | suggested English | "
                            "how to handle | literal words to avoid): " + line)
            continue
        f += [""] * (6 - len(f))
        if not has_cjk(f[0]) or len(f[0]) < 2:
            problems.append("SLANG term must be Chinese, at least 2 characters: %s. A single "
                            "character would match inside ordinary words (蛋 in 鸡蛋) and spoil "
                            "them. Translate it right where it appears, keep the same word each "
                            "time, and add a FLAG line so a person knows." % f[0])
            continue
        rows.append({"term": f[0], "meaning": f[1], "tone": f[2], "default_en": f[3],
                     "strategy": f[4], "avoid": f[5]})
    return rows, problems


def parse_noslang(text):
    terms = []
    for raw in text.splitlines():
        line = raw.strip().lstrip("-*").strip()
        if line.upper().startswith("NOSLANG:"):
            terms += [t.strip() for t in re.split(r"[|,，/ ]+", line.split(":", 1)[1]) if t.strip()]
    return terms


def merge_noslang(book, terms):
    if not terms:
        return []
    have = book.slang_off()
    new = [t for t in terms if t not in have]
    if new:
        p = book.bible / "slang_off.txt"
        old = p.read_text(encoding="utf-8") if p.exists() else (
            "# Slang-table words that are always meant literally in this book. One per line.\n")
        p.write_text(old.rstrip("\n") + "\n" + "\n".join(new) + "\n", encoding="utf-8")
        return ["Slang table switched off for this book: " + ", ".join(new)]
    return []


def merge_slang(book, rows):
    """Add book-specific slang to bible/slang_extra.tsv. Existing entries are kept."""
    if not rows:
        return []
    path = book.bible / "slang_extra.tsv"
    have = read_tsv(path)
    terms = {r.get("term") for r in have}
    report = []
    added = 0
    for r in rows:
        if r["term"] in terms:
            report.append("Slang " + r["term"] + " is already in bible/slang_extra.tsv; kept the "
                          "existing line (edit the file to change it).")
            continue
        have.append(r)
        terms.add(r["term"])
        added += 1
    write_tsv(path, SLANG_HEADER, have,
              ["This book's own slang, in-jokes and stand-in words. Shown in every task where the "
               "term appears; overrides the shared table. avoid = literal English words "
               "(comma-separated) that would mean a word-for-word translation. TAB-separated."])
    if added:
        report.insert(0, "Added " + str(added) + " slang entr" + ("y" if added == 1 else "ies")
                      + " to bible/slang_extra.tsv.")
    return report


def parse_flags(text):
    """FLAG: P10 | why a human should look at this paragraph."""
    flags = []
    for raw in text.splitlines():
        line = raw.strip().lstrip("-*").strip()
        if line.upper().startswith("FLAG:"):
            f = [x.strip() for x in line.split(":", 1)[1].split("|", 1)]
            para = f[0] if len(f) > 1 else ""
            note = f[1] if len(f) > 1 else f[0]
            if note and note.strip().lower().strip(".。!") not in ("none", "n/a", "na", "no",
                                                                     "nothing", "无", "没有", "-", ""):
                flags.append({"para": para, "note": note})
    return flags


def found_in_book(book, terms, chars, near=""):
    """Drop TERM/CHAR lines whose Chinese is nowhere in the book: such a line can never match
    (青雲宗 written instead of the book's 青云宗) and would fail silently. `near` (the current
    passage) is searched first so the whole book is only read when needed."""
    whole = [None]
    problems = []

    def found(v):
        if v in near:
            return True
        if whole[0] is None:
            parts = []
            for ch in book.cfg["chapters"]:
                for cid in ch["chunks"]:
                    src = book.source(cid)
                    parts.append(src.get("title") or "")
                    parts.extend(src["paras"])
            whole[0] = "\n".join(parts)
        return v in whole[0]

    kept = ([], [])
    for rows, out_rows, alias in ((terms, kept[0], None), (chars, kept[1], "aliases")):
        for r in rows:
            vs = variants(r["zh"], r.get(alias) if alias else "")
            if any(found(v) for v in vs):
                out_rows.append(r)
            else:
                problems.append("%s is not in the book. The first field must be the Chinese exactly "
                                "as the book writes it (simplified 青云宗, not 青雲宗), even when the "
                                "translation uses other characters. Line not saved." % r["zh"])
    return kept[0], kept[1], problems


def merge_bible(book, terms, chars):
    """Add new entries. Never overwrite existing ones; record conflicts instead."""
    report = []
    conflicts = read_tsv(book.bible / "conflicts.tsv")

    gl = book.glossary()
    by_zh = {}
    for r in gl:
        for v in variants(r.get("zh")):
            by_zh[v] = r
    added = 0
    for t in terms:
        if len(t["zh"]) == 1:
            report.append("SKIPPED single-character term %s: it would match inside other words "
                          "(道 in 一道菜). Use a longer form." % t["zh"])
            continue
        old = by_zh.get(t["zh"])
        if old:
            if old.get("en", "").lower() != t["en"].lower():
                conflicts.append({"zh": t["zh"], "existing": old.get("en", ""),
                                  "proposed": t["en"], "file": "glossary"})
                report.append("CONFLICT kept existing glossary entry %s = %s (proposed: %s). "
                              "Use the existing one. Only if the user wants the change: "
                              "`%s rename %s \"%s\"`." % (t["zh"], old.get("en"), t["en"],
                                                          py_cmd(), t["zh"], t["en"]))
            continue
        same_en = [r for r in gl if r.get("en", "").lower() == t["en"].lower()]
        if same_en:
            report.append("WARNING: %s and %s now share the English '%s'."
                          % (t["zh"], same_en[0].get("zh"), t["en"]))
        gl.append(t)
        by_zh[t["zh"]] = t
        added += 1
    write_tsv(book.bible / "glossary.tsv", ["zh", "en", "type", "note"], gl,
              ["Glossary. One term per line. zh may list variants as A/B. Columns are TAB-separated."])

    cs = book.characters()
    by_name = {}
    for r in cs:
        for v in variants(r.get("zh"), r.get("aliases")):
            by_name[v] = r
    cadded = 0
    for c in chars:
        old = by_name.get(c["zh"])
        if old:
            if old.get("en", "").lower() != c["en"].lower():
                conflicts.append({"zh": c["zh"], "existing": old.get("en", ""),
                                  "proposed": c["en"], "file": "characters"})
                report.append("CONFLICT kept existing character %s = %s (proposed: %s). "
                              "Use the existing one. Only if the user wants the change: "
                              "`%s rename %s \"%s\"`." % (c["zh"], old.get("en"), c["en"],
                                                          py_cmd(), c["zh"], c["en"]))
            elif c["gender"] and not old.get("gender"):
                old["gender"] = c["gender"]
            continue
        cs.append(c)
        for v in variants(c["zh"], c["aliases"]):
            by_name[v] = c
        cadded += 1
    write_tsv(book.bible / "characters.tsv", ["zh", "aliases", "en", "gender", "note"], cs,
              ["Characters. aliases = other names/nicknames separated by /. "
               "gender decides he/she/they. TAB-separated."])
    if conflicts:
        write_tsv(book.bible / "conflicts.tsv", ["zh", "existing", "proposed", "file"], conflicts,
                  ["Proposed names that disagreed with the bible. Resolve by editing the bible, "
                   "then delete the line here."])
    report.insert(0, "Added %d term(s) and %d character(s)." % (added, cadded))
    return report


def cmd_add(args):
    book = workspace_from_args(args)
    path = Path(args.file)
    if not path.is_absolute() and not path.exists():
        path = book.ws / args.file
    if not path.exists():
        fail("Notes file not found: " + args.file)
    text = path.read_text(encoding="utf-8")
    _, terms, chars, problems = parse_notes(text, book.lang, book.keep_chars())
    terms, chars, missing = found_in_book(book, terms, chars)
    problems += missing
    slang_rows, slang_problems = parse_slang(text)
    for p in problems + slang_problems:
        out("SKIPPED: " + p)
    for line in (merge_bible(book, terms, chars) + merge_slang(book, slang_rows)
                 + merge_noslang(book, parse_noslang(text))):
        out(line)
    nxt("Run `" + py_cmd() + " next` to start translating (or add more names first). If a task "
        "file is already open, `" + py_cmd() + " next --force` refreshes it.")


# ------------------------------------------------------------ task files

def read_md_section(path):
    p = Path(path)
    if not p.exists():
        return ""
    text = p.read_text(encoding="utf-8")
    text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    return text.strip()


def lang_text(lang, name):
    """A text module for the target language. lang/<lang>/<name> wins; English (and any
    language without its own copy of translation_rules.md / names.md) uses core/."""
    own = SKILL_DIR / "lang" / lang / name
    if own.exists():
        return read_md_section(own)
    if name in ("translation_rules.md", "names.md"):
        return read_md_section(SKILL_DIR / "core" / name)
    return ""


def genre_text(lang, genre):
    """Genre notes: lang/<lang>/genres/<genre>.md, else genres/<genre>.md for English.
    The English genre notes are not shown for other languages (they give English renderings)."""
    own = SKILL_DIR / "lang" / lang / "genres" / (genre + ".md")
    if own.exists():
        return read_md_section(own)
    if lang == "en":
        return read_md_section(SKILL_DIR / "genres" / (genre + ".md"))
    return "(No %s notes for this genre yet. Follow the rules above.)" % lang_info(lang)["name"]


def pick_examples(genre, limit=3, lang="en"):
    text = read_md_section(SKILL_DIR / "lang" / lang / "examples.md")
    sections = re.split(r"(?m)^## ", text)
    picked_genre = []
    picked_general = []
    for sec in sections[1:]:
        head = sec.split("\n", 1)[0]
        m = re.match(r"\[([^\]]+)\]", head)
        tags = [t.strip() for t in m.group(1).split(",")] if m else ["general"]
        if genre in tags:
            picked_genre.append("### " + sec.strip())
        elif "general" in tags:
            picked_general.append("### " + sec.strip())
    chosen = (picked_genre[:2] + picked_general)[:limit]
    return "\n\n".join(chosen)


def book_examples(book, limit=3):
    """Examples taken from this book (made with `pin`), newest last. These beat generic ones."""
    text = read_md_section(book.bible / "examples.md")
    sections = ["### " + sec.strip() for sec in re.split(r"(?m)^## ", text)[1:] if sec.strip()]
    return sections[-limit:]


def examples_block(book, genre):
    own = book_examples(book)
    parts = []
    if own:
        parts.append("From this book, approved by the reader. Match this voice: its rhythm, "
                     "word choice and how much it compresses. But imitating the voice never "
                     "justifies adding, dropping or changing meaning, cutting the subject of a "
                     "sentence, or softening the original's punctuation (keep its ! and ?). "
                     "Calm passages stay calm even if the examples are tense.\n\n"
                     + "\n\n".join(own))
    if len(own) < 3:
        generic = pick_examples(genre, 3 - len(own), book.lang)
        if generic:
            parts.append("General examples (their names are invented - never use them):\n\n"
                         + generic)
    return "\n\n".join(parts) or "(none)"


def entries_in(text, rows, alias_field=None):
    hits = []
    for r in rows:
        vs = variants(r.get("zh"), r.get(alias_field) if alias_field else "")
        found = [v for v in vs if v and v in text]
        if found:
            hits.append((r, found))
    return hits


def md_table(header, rows):
    if not rows:
        return "(none)"
    lines = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    for r in rows:
        lines.append("| " + " | ".join(str(x).replace("|", "/") for x in r) + " |")
    return "\n".join(lines)


def passage_text(src):
    """The Chinese the model actually translates: the title only on a chapter's first part."""
    title = src.get("title") if src["part"] == 1 else ""
    return (title or "") + "\n" + "\n".join(src["paras"])


def numbered_source(src):
    lines = []
    if src["part"] == 1 and src.get("title"):
        lines.append("[[T]] " + src["title"])
        lines.append("")
    for i, p in enumerate(src["paras"], 1):
        lines.append("[[P%d]] %s" % (i, p))
        lines.append("")
    return "\n".join(lines).strip()


def parse_output(text):
    """Return (blocks: list of (marker, text)), problems."""
    blocks = []
    problems = []
    cur = None
    for i, raw in enumerate(text.splitlines(), 1):
        if FENCE_RE.match(raw):
            continue
        m = MARK_RE.match(raw)
        if m:
            cur = [m.group(1), m.group(2).strip()]
            blocks.append(cur)
        elif raw.strip():
            if cur is None:
                problems.append("Line %d is outside any [[..]] marker (remove commentary): %s"
                                % (i, raw.strip()[:80]))
            else:
                cur[1] = (cur[1] + " " + raw.strip()).strip()
    return [(b[0], b[1]) for b in blocks], problems


def context_block(book, cid):
    ids = book.chunk_ids()
    idx = ids.index(cid)
    parts = []
    syn = read_md_section(book.bible / "synopsis.md")
    syn_lines = [ln for ln in syn.splitlines() if ln.strip() and not ln.startswith("#")]
    if syn_lines:
        parts.append("Book overview (from the bible):\n" + syn)
    sums = [r for r in book.summaries() if r.get("chunk", "") < cid]
    if sums:
        recent = sums[-6:]
        parts.append("Recent passages:\n" + "\n".join(
            "- (ch.%s) %s" % (r.get("chapter"), r.get("summary")) for r in recent))
    if idx > 0 and ids[idx - 1] in book.done() and book.tr_path(ids[idx - 1]).exists():
        prev = ids[idx - 1]
        psrc = book.source(prev)["paras"]
        blocks, _ = parse_output(book.tr_path(prev).read_text(encoding="utf-8"))
        ptr = [t for m, t in blocks if m != "T"]
        pairs = []
        for k in range(max(0, len(psrc) - 3), len(psrc)):
            zh = psrc[k]
            en = ptr[k] if k < len(ptr) else ""
            pairs.append("ZH: " + zh + "\n" + lang_info(book.lang)["label"] + ": " + en)
        parts.append("End of the previous passage (already translated - continue its voice):\n\n"
                     + "\n\n".join(pairs))
    return "\n\n".join(parts) if parts else "(This is the start of the book.)"


def slang_hits(book, text, name_hits=None):
    """Slang terms in the text. A slang word that only appears inside a longer glossary name
    (逆袭 in 逆袭系统) does not count; a term that is itself a name still does."""
    slang = book.slang()
    terms = {r.get("term") for r in slang}
    if name_hits is None:
        name_hits = entries_in(text, book.glossary()) + \
            entries_in(text, book.characters(), "aliases")
    plain = text
    for name in sorted({v for _, f in name_hits for v in f}, key=len, reverse=True):
        if name not in terms:
            plain = plain.replace(name, " ")
    return entries_in(plain, [dict(r, zh=r.get("term", "")) for r in slang])


def literal_slang(book, zh, en):
    """(term, word) pairs where a stand-in term's literal English shows up in the translation."""
    found = []
    for r, _ in slang_hits(book, zh):
        for w in (r.get("avoid") or "").split(","):
            w = w.strip()
            if w and re.search(r"(?<![A-Za-z])" + re.escape(w) + r"(?![A-Za-z])", en or "", re.I):
                found.append((r.get("term"), w))
    return found


def reference_tables(book, text):
    g_hits = entries_in(text, book.glossary())
    c_hits = entries_in(text, book.characters(), "aliases")
    # a slang word that only appears inside a glossary name (逆袭 in 逆袭系统) is not slang here
    s_hits = slang_hits(book, text, g_hits + c_hits)
    gl = md_table(["中文 (found)", book.lname + " - use exactly", "type", "note"],
                  [["/".join(f), r.get("en"), r.get("type"), r.get("note")] for r, f in g_hits])
    ch = md_table(["中文 (found)", book.lname, "gender", "note"],
                  [["/".join(f), r.get("en"), r.get("gender"), r.get("note")] for r, f in c_hits])
    suggest = "suggested " + book.lname
    sl = md_table(["term", "meaning", "tone", suggest, "how to handle",
                   "never write (literal)"],
                  [[r.get("term") + (" (this book)" if r.get("book") else ""), r.get("meaning"),
                    r.get("tone"), r.get("default_en"), r.get("strategy"), r.get("avoid", "")]
                   for r, _ in s_hits])
    return gl, ch, sl, len(s_hits)


def write_task(book, cid):
    src = book.source(cid)
    text = passage_text(src)
    gl, ch, sl, n_slang = reference_tables(book, text)
    genre = book.cfg.get("genre", "general")
    lang = book.lang
    rules = lang_text(lang, "translation_rules.md")
    names = lang_text(lang, "names.md")
    gmod = genre_text(lang, genre)
    style = lang_text(lang, "style_guide.md")
    examples = examples_block(book, genre)
    title_note = ("This is the first passage of a chapter: translate the chapter title as [[T]]."
                  if src["part"] == 1 and src.get("title") else
                  "This passage is not the start of a chapter: there is no [[T]] line.")
    n = len(src["paras"])
    body = """# TRANSLATION TASK - passage {cid}
{where} - part {part} of {parts} - {n} paragraphs

## What to do
1. Read this whole file once. Then translate the SOURCE TEXT at the bottom into {lname}.
2. Write ONLY the translation into `work/current_output.md`. Format: every block starts with the
   same marker as the source ([[T]] for a title, then [[P1]] to [[P{n}]]), one blank line between blocks.
3. Keep all {n} paragraphs, in the same order. Never merge, split, skip or summarise.
4. No comments, no notes, no headings, no code fences - only marked translated paragraphs.
5. Use the names in "Must-use names" exactly as written.
6. Then run: `{cmd} check`
{title_note}

## Must-use names and terms (found in this passage)
{gl}

## Characters in this passage (use the right he/she)
{ch}

## Internet slang / genre jargon found ({n_slang})
{sl}

## Story context
{context}

## Translation rules
{rules}

{names}

## Genre notes: {genre}
{gmod}

## {lname} style
{style}

## Examples of the target quality
{examples}

## SOURCE TEXT
{source}
""".format(cid=cid,
           where=("Front matter (title page / blurb)" if src.get("front")
                  else "Chapter %d%s" % (src["chapter"],
                                          (" (" + src["title"] + ")") if src.get("title") else "")),
           part=src["part"], parts=src["parts"], n=n, cmd=py_cmd(), title_note=title_note,
           gl=gl, ch=ch, n_slang=n_slang, sl=sl, context=context_block(book, cid),
           rules=rules, names=names, genre=genre, gmod=gmod, style=style,
           examples=examples, source=numbered_source(src), lname=book.lname)
    book.work.mkdir(exist_ok=True)
    (book.work / "current_task.md").write_text(show_paths(body), encoding="utf-8")
    (book.work / "current_output.md").write_text("", encoding="utf-8")
    (book.work / "current_notes.md").write_text("", encoding="utf-8")


SPOT_REVIEW = """# SPOT REVIEW - passage {cid}

The script picked the paragraphs where meaning errors are most likely ({picked}): numbers or
negation that differ between ZH and DRAFT, slang translated word for word, plus paragraphs with
yes/no choices, titles, or who-does-what-to-whom structures.
For each one below, compare DRAFT with ZH as if someone else had written the draft.

Check:
- **Who does what to whom.** Subject and object not swapped (我打了他 ≠ he hit me; 把/被 sentences).
- **Yes/no and negation.** 确认/取消, 是/否, 不/没/别/未 - is the {lname} saying the same, not the opposite?
- **Numbers, amounts, times, ranks.**
- **Title prefixes.** 代 = acting, 副 = deputy/vice, 前 = former (秦代掌门 = Acting Sect Leader Qin).
- **Tone.** Insult stays insult, sarcasm stays sarcastic, humble stays humble.
- **Every clause there, nothing added.**
{extra_checks}- **Slang and stand-in words** translated by their real meaning, not word for word.
- **Reads fine but makes no sense** (a herb growing on someone's arm, gold being plucked off a
  beast): that is usually a stand-in word nobody listed yet. Fix it, and add a SLANG line to
  your notes so every later passage gets it right.

If a paragraph is wrong, fix **only that paragraph** in `work/current_output.md` (keep its marker).
Do not touch the other paragraphs. If everything is right, change nothing.
Then run: `{cmd} check`

## Must-use names and terms
{gl}

## Characters
{ch}

## PARAGRAPHS TO CHECK
{pairs}
"""


# Extra review checks for a target language (the English review is unchanged).
REVIEW_EXTRA = {
    "ja": ("- **Chinese in Japanese clothing.** The most common slip: a Chinese idiom, net phrase or "
           "measure word copied\n  into kanji. Grammatical, but no Japanese writer would say it: "
           "火が眉毛まで燃える (火烧眉毛), 頭に水が入る\n  (脑子进水), 一歩進んでは一歩見る (走一步看一步), "
           "一張りの顔 (一张脸), 泣くより醜い笑み (比哭还难看), AI顔交換\n  (AI换脸). Rewrite it the "
           "way Japanese says it (尻に火がつく, 頭がどうかしている, 出たとこ勝負, 顔, 泣き笑い, "
           "ディープフェイク).\n"),
}


def review_mode(book):
    mode = book.cfg.get("review")
    if mode in ("off", "spot", "full"):
        return mode
    return "full" if book.cfg.get("polish") else "off"


RISK_PATTERNS = [
    (r"确认|取消|同意|拒绝|是否|答应|不行|可以|不要|别", 2),   # yes/no, choices, prohibitions
    (r"[不没未莫勿非无]", 1),                                  # negation
    (r"[0-9０-９]+|[零一二两三四五六七八九十百千万亿]{2,}", 1),  # numbers
    (r"代[\u4e00-\u9fff]{1,2}[主长令首帅]|副|前任|大人|陛下|朕|本官|本座|老夫", 1),  # titles
    (r"把|被|让|给|替|向", 1),                                  # who-does-what-to-whom markers
    (r"[“\"「]", 1),                                             # dialogue
]


def risky_paragraphs(paras, limit):
    scored = []
    for i, p in enumerate(paras, 1):
        if cjk_count(p) < 12:
            continue
        score = sum(w for pat, w in RISK_PATTERNS if re.search(pat, p))
        scored.append((score, len(p), i))
    scored.sort(reverse=True)
    return sorted(i for _, _, i in scored[:limit])


def write_polish_task(book, cid):
    src = book.source(cid)
    draft_text = (book.work / "current_output.md").read_text(encoding="utf-8")
    (book.work / "draft_output.md").write_text(draft_text, encoding="utf-8")
    blocks, _ = parse_output(draft_text)
    draft = dict(blocks)
    text = passage_text(src)
    gl, ch, sl, _ = reference_tables(book, text)
    style = lang_text(book.lang, "style_guide.md")
    spot = review_mode(book) == "spot"
    pairs = []
    if spot:
        n_paras = len(src["paras"])
        must = [i for i, p in enumerate(src["paras"], 1)
                if number_mismatch(p, draft.get("P%d" % i, ""), book.lang)]
        neg = [i for i, p in enumerate(src["paras"], 1)
               if negation_mismatch(p, draft.get("P%d" % i, ""), book.lang)]
        must += [i for i, p in enumerate(src["paras"], 1)
                 if literal_slang(book, p, draft.get("P%d" % i, ""))]
        picked = sorted(set(must) | set(neg[:6]) |
                        set(risky_paragraphs(src["paras"], min(6, max(2, n_paras // 4)))))
        for i in picked:
            pairs.append("[[P%d]]\nZH: %s\nDRAFT: %s" % (i, src["paras"][i - 1],
                                                       draft.get("P%d" % i, "")))
        body = SPOT_REVIEW.format(cid=cid, cmd=py_cmd(), picked=", ".join("P%d" % i for i in picked),
                                  gl=gl, ch=ch, pairs="\n\n".join(pairs), lname=book.lname,
                                  extra_checks=REVIEW_EXTRA.get(book.lang, ""))
        (book.work / "current_task.md").write_text(show_paths(body), encoding="utf-8")
        return
    if src["part"] == 1 and src.get("title"):
        pairs.append("[[T]]\nZH: %s\nDRAFT: %s" % (src["title"], draft.get("T", "")))
    for i, p in enumerate(src["paras"], 1):
        pairs.append("[[P%d]]\nZH: %s\nDRAFT: %s" % (i, p, draft.get("P%d" % i, "")))
    body = """# REVIEW TASK - passage {cid}

Below, every paragraph has the Chinese original (ZH) and a draft {lname} translation (DRAFT).
Go through them one by one.

## Step 1 - meaning (the most important part)
For every paragraph, compare DRAFT with ZH and fix any of these:
- **Who does what to whom.** Subject and object not swapped (我打了他 ≠ he hit me).
- **Yes/no and negation.** 确认/取消, 是/否, 不/没/别/未, a question turned into a statement.
- **Numbers, amounts, times, ranks.**
- **Title prefixes.** 代 = acting, 副 = deputy/vice, 前 = former, 老/小 = old/young: 秦代掌门 is
  "Acting Sect Leader Qin", not a person called "Qin Dai".
- **Tone.** An insult stays an insult, sarcasm stays sarcastic, a humble line stays humble.
- **Left out or added.** Every clause of ZH is there, nothing extra (no added greetings or explanations).
- **Slang and stand-in words.** An innocent word used in place of a rude one (牛至 for 牛子,
  河蟹 for 和谐) must not be translated literally: check the slang table. If a sentence reads
  fine but makes no sense in the scene, it is probably a stand-in nobody listed yet: fix it and
  add a SLANG line to your notes.
- **Jokes and wordplay.** Is the joke still funny in {lname}? If a pun was lost, try to rebuild it
  with {a_lname} word that has the same double meaning. If you can't, keep the meaning.
{extra_checks}
## Step 2 - {lname}
Then make it read like a good {lname} novel: natural rhythm, varied sentences, clear dialogue,
no translationese (see the style table). Keep the author's tone; don't add flourishes.

## Step 3 - write it
Overwrite `work/current_output.md` with the full revised text, same markers
([[T]] if present, [[P1]] ... [[P{n}]]), one block per paragraph, nothing else.
Then run: `{cmd} check`
In your notes later, add a FLAG line for any paragraph you are still unsure about.

## Must-use names and terms
{gl}

## Characters
{ch}

## Slang found
{sl}

## {lname} style
{style}

## PARAGRAPHS
{pairs}
""".format(cid=cid, n=len(src["paras"]), cmd=py_cmd(), gl=gl, ch=ch, sl=sl, style=style,
           pairs="\n\n".join(pairs), lname=book.lname,
           a_lname=("an " if book.lname[0] in "AEIOU" else "a ") + book.lname,
           extra_checks=REVIEW_EXTRA.get(book.lang, ""))
    (book.work / "current_task.md").write_text(show_paths(body), encoding="utf-8")


# ------------------------------------------------------------- next/check

def trial_stop(book, cid):
    if not book.cfg.get("trial"):
        return False
    # the trial covers any front matter plus the first real chapter
    trial_ids = []
    for ch in book.cfg["chapters"]:
        if ch.get("skip"):
            continue
        trial_ids.extend(ch["chunks"])
        if not ch.get("front"):
            break
    return cid not in trial_ids and all(c in book.done() for c in trial_ids)


def cmd_next(args):
    book = workspace_from_args(args)
    cur = book.cfg.get("current")
    if cur and not args.force:
        out("Passage %s is still open (stage: %s)." % (cur, book.cfg.get("stage")))
        out("Task file: " + str(book.work / "current_task.md"))
        nxt("Finish it: write work/current_output.md, then run `" + py_cmd() + " check`. "
            "(Use `next --force` to rebuild the task file.)")
        return
    done = book.done()
    todo = [c for c in book.chunk_ids() if c not in done]
    if args.force and cur:
        todo = [cur] + [c for c in todo if c != cur]
    if not todo:
        out("Every passage is translated.")
        nxt("Run `" + py_cmd() + " build` and give the user the finished files.")
        return
    cid = todo[0]
    if trial_stop(book, cid):
        out("TRIAL FINISHED: the first chapter is translated.")
        nxt("Run `" + py_cmd() + " build` and `" + py_cmd() + " flags`. Show the user the result "
            "and the flags, tell them how many chapters the book has (so they can judge the cost "
            "from what this chapter used), and ask: should any names or the style change, and "
            "which 2-3 short bits (dialogue, calm narration, action) should become examples? See SKILL.md "
            "step 4: save them with `" + py_cmd() + " pin <passage> <P3-P6> --why \"...\"`, or with "
            "`--en <file>` when the user (or a second model) edited the " + book.lname + ". "
            "Then ask whether to continue. "
            "Only if they say yes: `" + py_cmd() + " set trial false`, then `" + py_cmd() + " next`.")
        return
    write_task(book, cid)
    book.cfg["current"] = cid
    book.cfg["stage"] = "translate"
    book.save()
    src = book.source(cid)
    done_n = len(done)
    total = len(book.chunk_ids())
    out("Passage %s ready (%s, part %d/%d, %d paragraphs). Progress: %d/%d."
        % (cid, src.get("title") or ("front matter" if src.get("front") else "chapter %d" % src["chapter"]),
           src["part"], src["parts"],
           len(src["paras"]), done_n, total))
    out("Task file: " + str(book.work / "current_task.md"))
    nxt("Read work/current_task.md and follow it: write the translation to "
        "work/current_output.md, then run `" + py_cmd() + " check`.")


def run_checks(book, cid):
    src = book.source(cid)
    path = book.work / "current_output.md"
    errors = []
    warnings = []
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    if not text.strip():
        return ["work/current_output.md is empty. Write the translation there first."], [], []
    blocks, problems = parse_output(text)
    errors.extend(problems)
    expected = []
    if src["part"] == 1 and src.get("title"):
        expected.append("T")
    expected += ["P%d" % i for i in range(1, len(src["paras"]) + 1)]
    got = [m for m, _ in blocks]
    seen = Counter(got)
    dups = [m for m, c in seen.items() if c > 1]
    if dups:
        errors.append("Duplicate markers: " + ", ".join(dups))
    missing = [m for m in expected if m not in seen]
    extra = [m for m in got if m not in expected]
    if missing:
        errors.append("Missing paragraphs: " + ", ".join(missing[:20]) +
                      (" ..." if len(missing) > 20 else ""))
    if extra:
        errors.append("Markers that do not exist in the source: " + ", ".join(extra[:20]))
    if not missing and not extra and not dups and got != expected:
        errors.append("Paragraphs are out of order. Keep the source order.")
    tr = dict(blocks)
    src_map = {"T": src.get("title", "")} if "T" in expected else {}
    for i, p in enumerate(src["paras"], 1):
        src_map["P%d" % i] = p
    lang = book.lang
    lname = book.lname
    keep = book.keep_chars() + "".join(r.get("en", "") for r in book.glossary() + book.characters()) \
        if lang != "en" else ""
    short_limit, long_limit = LENGTH_LIMITS.get(lang, LENGTH_LIMITS["en"])
    total_zh = 0
    total_en = 0
    for m in expected:
        if m not in tr:
            continue
        en = tr[m]
        zh = src_map[m]
        if not en and zh.strip():
            errors.append("[[%s]] is empty." % m)
            continue
        problem, _ = leftover_chinese(en, lang, keep)
        if problem:
            errors.append("[[%s]] %s" % (m, problem))
        elif lang == "ja" and cjk_count(zh) >= 12 and len(en) >= 20 and not KANA_RE.search(en):
            errors.append("[[%s]] has no kana at all. If it is still Chinese, translate it. If it "
                          "is Japanese, it reads like a notice board, not a novel: add the particles "
                          "and endings a Japanese sentence needs (が, は, を, だ...)." % m)
        extra_nums = number_mismatch(zh, en, lang)
        for term, word in literal_slang(book, zh, en):
            warnings.append("Slang check: [[%s]] has %s, a slang/stand-in word, and the %s "
                            "says '%s' - is that a word-for-word translation? See the slang table "
                            "in the task file. (Fine if it really is meant literally here.)"
                            % (m, term, lname, word))
        if extra_nums:
            warnings.append("Number check: [[%s]] says %s in %s, but the Chinese has no such "
                            "number. Check it against the original; if the %s is right, keep it." % (
                                m, ", ".join(str(v) for v in extra_nums), lname, lname))
        zc = cjk_count(zh)
        wc = text_size(en, lang)
        if m != "T":
            total_zh += zc
            total_en += wc
        if zc >= LENGTH_MIN_ZH.get(lang, 30):
            ratio = wc / float(zc)
            if ratio < (SHORT_PARA_LIMIT.get(lang, short_limit) if zc < 30 else short_limit):
                warnings.append("[[%s]] is much shorter than the original - check nothing "
                                "was left out." % m)
            elif ratio > long_limit:
                warnings.append("[[%s]] is much longer than the original - check nothing "
                                "was added." % m)
        low = en.lower()
        for ph in (JA_NOTE_PHRASES if lang == "ja" else NOTE_PHRASES):
            if ph in low:
                warnings.append("[[%s]] contains a note ('%s'). Notes are not allowed in the "
                                "text; put the meaning into the sentence." % (m, ph))
                break
    if total_zh >= 200 and total_en / float(total_zh) < short_limit:
        errors.append("The whole passage is far too short for the original. It looks "
                      "summarised. Translate every sentence.")
    first = blocks[0][1].lower() if blocks else ""
    for ph in (JA_META_PHRASES if lang == "ja" else META_PHRASES):
        if first.startswith(ph):
            errors.append("Remove the commentary at the start ('%s...')." % ph)
            break
    # glossary / character name use
    full_src = "\n".join(src_map.values())
    full_en = "\n".join(tr.values()).lower().replace("-", " ")
    rows = [(r, f) for r, f in entries_in(full_src, book.glossary())]
    # characters: only when the main name is there. A nickname or form of address (陆师兄 for
    # 陆香君) is rightly translated as that form (陸師兄 / Senior Brother Lu), not the full name.
    rows += [(r, f) for r, f in entries_in(full_src, book.characters())]
    for r, f in rows:
        en = (r.get("en") or "").strip()
        if not en:
            continue
        options = [o.strip().lower().replace("-", " ") for o in en.split("/") if o.strip()]
        if not any(o in full_en for o in options):
            warnings.append("Name check: %s should appear as '%s' (fine if you used he/she or "
                            "another form on purpose)." % ("/".join(f), en))
    for pattern, min_hits, advice in (STYLE_LINT if lang == "en" else
                                      JA_STYLE_LINT if lang == "ja" else []):
        where = [m for m, t in blocks if re.search(pattern, t, re.I)]
        total = sum(len(re.findall(pattern, t, re.I)) for _, t in blocks)
        if total >= min_hits:
            warnings.append("Style: %s (in %s)" % (advice, ", ".join("[[%s]]" % w for w in where[:6])))
    return errors, warnings, blocks


def cmd_check(args):
    book = workspace_from_args(args)
    cid = book.cfg.get("current")
    if not cid:
        fail("No passage is open.", "Run `" + py_cmd() + " next`.")
    errors, warnings, _ = run_checks(book, cid)
    if errors:
        out("CHECK FAILED for passage %s:" % cid)
        for e in errors:
            out("  ERROR: " + e)
        for w in warnings:
            out("  WARNING: " + w)
        nxt("Fix work/current_output.md (keep the [[..]] markers) and run `" + py_cmd() +
            " check` again.")
        sys.exit(1)
    out("FORMAT CHECK PASSED for passage %s. (This checks paragraphs, leftover Chinese, length, "
        "names and common style slips. It cannot tell whether the meaning is right.)" % cid)
    for w in warnings:
        out("  WARNING: " + w)
    if warnings:
        out("Look at the warnings. Fix real mistakes in work/current_output.md; ignore the rest. "
            "Never make a correct sentence worse just to silence a warning.")
    ln = book.lname
    pad = " " * max(0, 7 - len(ln))
    notes_hint = ("write work/current_notes.md with:\n"
                  "  SUMMARY: one or two English sentences about what happened in this passage\n"
                  "  TERM: 中文 | " + ln + " | type | note     " + pad +
                  "(one line per NEW name/term you translated)\n"
                  "  CHAR: 中文 | " + ln + " | gender | note    " + pad + "(one line per NEW character)\n"
                  "  SLANG: 中文 | meaning | tone | " + ln +
                  " | how to handle | literal words to avoid\n"
                  "         (one line per NEW slang word, in-joke or stand-in word this book uses "
                  "again and again)\n"
                  "  FLAG: P10 | why a human should check it  (a pun you could not keep, a line "
                  "you are unsure of)\n"
                  "then run `" + py_cmd() + " accept`.")
    if review_mode(book) != "off" and book.cfg.get("stage") == "translate":
        nxt("The review pass is on: run `" + py_cmd() + " review`, follow work/current_task.md, "
            "check again; after that " + notes_hint)
    else:
        nxt("Now " + notes_hint)


def cmd_polish(args):
    book = workspace_from_args(args)
    cid = book.cfg.get("current")
    if not cid:
        fail("No passage is open.", "Run `" + py_cmd() + " next`.")
    errors, _, _ = run_checks(book, cid)
    if errors:
        fail("The draft does not pass the check yet; polish needs a complete draft.",
             "Run `" + py_cmd() + " check` and fix the errors first.")
    write_polish_task(book, cid)
    book.cfg["stage"] = "polish"
    book.save()
    out("Review task written: " + str(book.work / "current_task.md"))
    out("The first draft is saved in work/draft_output.md.")
    nxt("Read work/current_task.md, overwrite work/current_output.md with the revised text, "
        "then run `" + py_cmd() + " check`.")


def cmd_accept(args):
    book = workspace_from_args(args)
    cid = book.cfg.get("current")
    if not cid:
        fail("No passage is open.", "Run `" + py_cmd() + " next`.")
    errors, _, _ = run_checks(book, cid)
    if errors:
        fail("The translation does not pass the check.",
             "Run `" + py_cmd() + " check` and fix the errors.")
    notes_path = book.work / "current_notes.md"
    notes = notes_path.read_text(encoding="utf-8") if notes_path.exists() else ""
    summary, terms, chars, problems = parse_notes(notes, book.lang, book.keep_chars())
    terms, chars, missing = found_in_book(book, terms, chars, passage_text(book.source(cid)))
    problems += missing
    if not summary:
        fail("work/current_notes.md needs a SUMMARY: line (one or two sentences about this "
             "passage). It keeps later passages consistent.",
             "Write the SUMMARY line (plus TERM:/CHAR: lines for new names), then run `"
             + py_cmd() + " accept` again.")
    for p in problems:
        out("SKIPPED: " + p)
    src = book.source(cid)
    book.tr_path(cid).parent.mkdir(exist_ok=True)
    book.tr_path(cid).write_text((book.work / "current_output.md").read_text(encoding="utf-8"),
                                 encoding="utf-8")
    sums = [r for r in book.summaries() if r.get("chunk") != cid]
    sums.append({"chunk": cid, "chapter": str(src["chapter"]), "summary": summary})
    sums.sort(key=lambda r: r["chunk"])
    write_tsv(book.ws / "summaries.tsv", ["chunk", "chapter", "summary"], sums)
    slang_rows, slang_problems = parse_slang(notes)
    for p in slang_problems:
        out("SKIPPED: " + p)
    for line in (merge_bible(book, terms, chars) + merge_slang(book, slang_rows)
                 + merge_noslang(book, parse_noslang(notes))):
        out(line)
    flags = parse_flags(notes)
    if flags:
        rows = [r for r in read_tsv(book.bible / "flags.tsv") if r.get("chunk") != cid]
        for f in flags:
            rows.append({"chunk": cid, "chapter": src.get("title") or (
                             "front matter" if src.get("front") else str(src["chapter"])),
                         "para": f["para"],
                         "note": f["note"]})
        rows.sort(key=lambda r: r["chunk"])
        write_tsv(book.bible / "flags.tsv", ["chunk", "chapter", "para", "note"], rows,
                  ["Places the translator was unsure about. Show these to the user."])
        out("Saved %d flag(s) for the user to look at." % len(flags))
    done = book.done()
    done.add(cid)
    book.cfg["done"] = sorted(done)
    book.cfg["current"] = None
    book.cfg["stage"] = None
    book.save()
    total = len(book.chunk_ids())
    out("Passage %s saved. Progress: %d/%d passages." % (cid, len(done), total))
    if args.stop:
        nxt("Stopped as requested. Run `" + py_cmd() + " next` to continue later.")
    else:
        nxt("Run `" + py_cmd() + " next` for the next passage.")


# ------------------------------------------------------------ status/set

def next_action(book):
    cur = book.cfg.get("current")
    if cur:
        return ("finish passage %s: write work/current_output.md, then `%s check`"
                % (cur, py_cmd()))
    if all(c in book.done() for c in book.chunk_ids()):
        return "everything is translated: `" + py_cmd() + " build`"
    return "`" + py_cmd() + " next`"


def cmd_status(args):
    book = workspace_from_args(args)
    done = book.done()
    ids = book.chunk_ids()
    out("Book: " + book.cfg["title"] + ("  ->  " + book.cfg["title_en"] if book.cfg.get("title_en") else ""))
    out("Workspace: " + str(book.ws))
    out("Genre: %s   Trial mode: %s   Review pass: %s" % (
        book.cfg.get("genre"), "on" if book.cfg.get("trial") else "off",
        review_mode(book)))
    out("Translating into: %s (%s)" % (book.lname, book.lang))
    out("Passages done: %d / %d" % (len(done), len(ids)))
    live = [ch for ch in book.cfg["chapters"] if not ch.get("skip")]
    full = sum(1 for ch in live if all(c in done for c in ch["chunks"]))
    out("Chapters fully done: %d / %d" % (full, len(live)))
    skipped = [str(ch["n"]) for ch in book.cfg["chapters"] if ch.get("skip")]
    if skipped:
        out("Left out: chapter(s) " + (", ".join(skipped) if len(skipped) <= 12 else
                                         ", ".join(skipped[:6]) + " ... " + skipped[-1] +
                                         " (%d chapters)" % len(skipped)))
    out("Glossary entries: %d   Characters: %d" % (len(book.glossary()), len(book.characters())))
    fl = read_tsv(book.bible / "flags.tsv")
    if fl:
        out("Flags for the user: %d (`%s flags`)" % (len(fl), py_cmd()))
    ex = book_examples(book, 100)
    out("Book examples: %d%s" % (len(ex), "" if ex else " (add some with `pin` after the trial)"))
    conf = read_tsv(book.bible / "conflicts.tsv")
    if conf:
        out("Unresolved name conflicts: %d (see bible/conflicts.tsv)" % len(conf))
    nxt(next_action(book))


def cmd_set(args):
    book = workspace_from_args(args)
    key = args.key
    if key not in SETTABLE:
        fail("You can set: " + ", ".join(SETTABLE))
    kind = SETTABLE[key]
    val = args.value
    if kind == "bool":
        if val.lower() in ("true", "on", "yes", "1"):
            val = True
        elif val.lower() in ("false", "off", "no", "0"):
            val = False
        else:
            fail("Use true or false.")
    elif kind == "int":
        val = int(val)
    elif kind == "review":
        val = val.lower()
        if val not in ("off", "spot", "full"):
            fail("Use off, spot or full.")
    elif kind == "lang":
        val = val.lower()
        if val not in LANGS:
            fail("Unknown target language. Use one of: " + ", ".join(LANGS))
        if book.done() or book.cfg.get("current") or len(book.glossary()) or len(book.characters()):
            fail("The target language can only be changed before anything is translated or "
                 "named. To translate this book into another language, set it up again with "
                 "`" + py_cmd() + " init <book> --lang " + val + " --name <new-folder-name>`.")
        key = "target_lang"
    if key == "keep_chars":  # adds characters; "none" clears the list
        val = "" if val.strip().lower() in ("none", "-") else \
            "".join(sorted(set(CJK_RE.findall(book.keep_chars() + val))))
    if key == "genre" and val not in GENRES:
        fail("Unknown genre. Use one of: " + ", ".join(GENRES))
    if key == "chunk_chars":
        out("Note: chunk size only applies to books set up after this change.")
    if key == "polish":  # old name: polish true == full review
        key, val = "review", ("full" if val else "off")
    book.cfg[key] = val
    book.save()
    out("%s = %s" % (key, val))
    nxt(next_action(book))


def cmd_pin(args):
    """Save some paragraphs (source + current English) as an example for this book."""
    book = workspace_from_args(args)
    cid = "%04d" % int(args.passage)
    if cid not in book.chunk_ids():
        fail("No passage " + cid)
    if book.tr_path(cid).exists():
        text = book.tr_path(cid).read_text(encoding="utf-8")
    elif book.cfg.get("current") == cid:
        text = (book.work / "current_output.md").read_text(encoding="utf-8")
    else:
        fail("Passage %s is not translated yet." % cid)
    m = re.match(r"^P?(\d+)(?:\s*-\s*P?(\d+))?$", args.paras.strip(), re.I)
    if not m:
        fail("Give paragraphs like P3-P6 or 3-6.")
    a = int(m.group(1))
    b = int(m.group(2) or a)
    if b < a or b - a > 5:
        fail("Pick 1 to 6 paragraphs in a row (e.g. P3-P6). Short examples work best.")
    src = book.source(cid)["paras"]
    tr = dict(parse_output(text)[0])
    if args.en:
        en_path = Path(args.en)
        if not en_path.exists():
            en_path = book.ws / args.en
        if not en_path.exists():
            fail("File not found: " + args.en)
        edited = dict(parse_output(en_path.read_text(encoding="utf-8"))[0])
        # accept the original numbering (P20-P22) or a renumbered one (P1-P3)
        if all(("P%d" % i) in edited for i in range(a, b + 1)):
            tr = edited
        elif all(("P%d" % (i - a + 1)) in edited for i in range(a, b + 1)):
            tr = {"P%d" % i: edited["P%d" % (i - a + 1)] for i in range(a, b + 1)}
        else:
            fail("The --en file must have one [[P..]] line for each paragraph P%d-P%d." % (a, b))
        for k in ("P%d" % i for i in range(a, b + 1)):
            if book.lang == "en" and has_cjk(tr[k]):
                fail("The edited English for %s still contains Chinese." % k)
            if book.lang != "en":
                problem, _ = leftover_chinese(tr[k], book.lang, book.keep_chars())
                if problem:
                    fail("The edited %s for %s %s" % (book.lname, k, problem))
    zh_lines = []
    en_lines = []
    for i in range(a, b + 1):
        if i > len(src):
            fail("Passage %s has only %d paragraphs." % (cid, len(src)))
        zh_lines.append("[[P%d]] %s" % (i - a + 1, src[i - 1]))
        en_lines.append("[[P%d]] %s" % (i - a + 1, tr.get("P%d" % i, "")))
    path = book.bible / "examples.md"
    old = path.read_text(encoding="utf-8") if path.exists() else (
        "# Examples from this book\n\n<!-- Made with `novel.py pin`. Edit the EN lines freely: "
        "the model copies this voice. The last 3 sections are used. Add a 'Why:' line if you like. -->\n")
    label = args.label or ("passage %s P%d-P%d" % (cid, a, b))
    if args.en and not args.no_apply and book.tr_path(cid).exists():
        blocks, _ = parse_output(book.tr_path(cid).read_text(encoding="utf-8"))
        blocks = [(m, tr.get(m, t) if m != "T" and a <= int(m[1:]) <= b else t) for m, t in blocks]
        book.tr_path(cid).write_text("\n\n".join("[[%s]] %s" % bt for bt in blocks) + "\n",
                                     encoding="utf-8")
        out("The edited English also replaced P%d-P%d in the finished passage %s. Run `%s build` "
            "again to see it in the book files." % (a, b, cid, py_cmd()))
    section = "\n## %s\nZH:\n%s\nEN:\n%s\n" % (label, "\n".join(zh_lines), "\n".join(en_lines))
    if args.why:
        section += "Why: %s\n" % args.why.strip()
    path.write_text(old.rstrip("\n") + "\n" + section, encoding="utf-8")
    out("Saved as a book example in %s:" % display_path(path))
    out(section.strip())
    nxt("New task files use it from the next passage on (`" + py_cmd() + " next --force` "
        "refreshes the open one). To use edited English instead of the current translation, run "
        "pin again with --en <file> and delete the older section from bible/examples.md.")


def cmd_rename(args):
    """Deliberately change the English for a name or term (CONFLICT only blocks accidental changes)."""
    book = workspace_from_args(args)
    zh = args.zh.strip()
    new_en = args.english.strip()
    if book.lang == "en" and (has_cjk(new_en) or not new_en):
        fail("The new English must not contain Chinese.")
    if book.lang != "en":
        problem, _ = leftover_chinese(new_en, book.lang, book.keep_chars())
        if problem or not new_en:
            fail("The new %s %s" % (book.lname, problem or "is empty."))
    found = None
    for fname, rows, header, alias in (
            ("glossary.tsv", book.glossary(), ["zh", "en", "type", "note"], None),
            ("characters.tsv", book.characters(), ["zh", "aliases", "en", "gender", "note"], "aliases")):
        for r in rows:
            if zh in variants(r.get("zh"), r.get(alias) if alias else ""):
                found = (fname, rows, header, r)
                break
        if found:
            break
    if not found:
        fail("%s is not in the glossary or character list. Add it with a TERM:/CHAR: line and "
             "`%s add <file>`." % (zh, py_cmd()))
    fname, rows, header, row = found
    old_en = row.get("en", "")
    row["en"] = new_en
    write_tsv(book.bible / fname, header, rows)
    conf = [c for c in read_tsv(book.bible / "conflicts.tsv") if c.get("zh") not in
            variants(row.get("zh"), row.get("aliases", ""))]
    if (book.bible / "conflicts.tsv").exists():
        write_tsv(book.bible / "conflicts.tsv", ["zh", "existing", "proposed", "file"], conf,
                  ["Proposed names that disagreed with the bible. Resolve by editing the bible, "
                   "then delete the line here."])
    out("%s: '%s' -> '%s' (in %s)" % (row.get("zh"), old_en, new_en, fname))
    names = variants(row.get("zh"), row.get("aliases", ""))
    touched = [cid for cid in sorted(book.done())
               if any(n in "\n".join([book.source(cid).get("title") or ""] + book.source(cid)["paras"])
                      for n in names)]
    if not touched:
        nxt(next_action(book))
        return
    if args.fix_done and old_en:
        pat = re.compile(r"(?<![A-Za-z])" + re.escape(old_en) + r"(?![A-Za-z])")
        changed = 0
        for cid in touched:
            pth = book.tr_path(cid)
            text = pth.read_text(encoding="utf-8")
            new_text, k = pat.subn(new_en, text)
            if k:
                pth.write_text(new_text, encoding="utf-8")
                changed += k
        out("Replaced '%s' with '%s' %d time(s) in %d translated passage(s): %s"
            % (old_en, new_en, changed, len(touched), ", ".join(touched)))
        nxt("Skim those passages for grammar around the new name (a/the, plural). Then " +
            next_action(book))
    else:
        out("Already translated with the old form: passage(s) " + ", ".join(touched))
        nxt("Either leave them, run `" + py_cmd() + " rename " + zh + ' "' + new_en +
            '" --fix-done` to swap the exact English words in those passages, or `' + py_cmd() +
            " redo <passage>` to retranslate one. Then " + next_action(book))


def cmd_set_char(args):
    """Change gender, note or nicknames of a character, e.g. set-char 苏晴 gender female."""
    book = workspace_from_args(args)
    if args.field not in ("gender", "note", "aliases"):
        fail("You can change: gender, note, aliases (for the English name use `rename`).")
    rows = book.characters()
    for r in rows:
        if args.zh in variants(r.get("zh"), r.get("aliases")):
            old = r.get(args.field, "")
            r[args.field] = args.value.strip()
            write_tsv(book.bible / "characters.tsv", ["zh", "aliases", "en", "gender", "note"], rows,
                      ["Characters. aliases = other names/nicknames separated by /. "
                       "gender decides he/she/they. TAB-separated."])
            out("%s %s: '%s' -> '%s'" % (r.get("zh"), args.field, old, r[args.field]))
            hint = ""
            if book.cfg.get("current"):
                hint = "Run `" + py_cmd() + " next --force` so the open task uses it. "
            nxt(hint + "Passages already translated keep the old version; use `" + py_cmd() +
                " redo <passage>` if one needs fixing. Then " + next_action(book))
            return
    fail("%s is not in the character list." % args.zh)


# ------------------------------------------------------------------ scan
# The model looks at suspicious words with several examples from the whole book and decides
# whether each is a stand-in (an innocent word used for a rude one) or meant literally.

SCAN_DONE_HEADER = ["term", "verdict", "confidence", "note"]


def scan_done(book):
    return {r.get("term"): r for r in read_tsv(book.bible / "scan_done.tsv")}


def book_paragraphs(book):
    """(chapter label, paragraph) for every paragraph that is not left out."""
    rows = []
    for ch in book.cfg["chapters"]:
        if ch.get("skip"):
            continue
        label = ch.get("title") or ("front matter" if ch.get("front") else "chapter %d" % ch["n"])
        for cid in ch["chunks"]:
            for p in book.source(cid)["paras"]:
                rows.append((label, p))
    return rows


CLEAN_EDGE = set("，。！？、；：…—“”‘’\"'（）()《》【】 \n的了着过在里上下被把呢吗吧啊呀哦嘛就也都又还是")


def occurrence_score(p, i, word):
    """How likely the match at p[i] is the word itself and not two words touching
    (拉«开车»门 = 拉开 + 车门, 召«开开»学 = 召开 + 开学). Higher is cleaner."""
    before = p[i - 1] if i > 0 else "\n"
    after = p[i + len(word)] if i + len(word) < len(p) else "\n"
    score = 0
    if before in CLEAN_EDGE or before in NOUN_BEFORE:
        score += 1
    if after in CLEAN_EDGE:
        score += 1
    return score


def spread_examples(paras, word, k, width=40):
    """Up to k examples from different parts of the book, whole-word matches first."""
    hits = []
    for lab, p in paras:
        i = p.find(word)
        while i >= 0:
            hits.append((occurrence_score(p, i, word), lab, p, i))
            i = p.find(word, i + 1)
    if not hits:
        return []

    def spread(rows, n):
        if len(rows) <= n:
            return rows
        step = (len(rows) - 1) / float(n - 1) if n > 1 else 0
        return [rows[int(round(j * step))] for j in range(n)]

    clean = [h for h in hits if h[0] >= 1]
    rest = [h for h in hits if h[0] < 1]
    chosen = spread(clean, k)
    if len(chosen) < k:
        chosen += spread(rest, k - len(chosen))
    order = {id(h): n for n, h in enumerate(hits)}
    chosen.sort(key=lambda h: order[id(h)])
    out_rows = []
    for score, lab, p, i in chosen:
        a, b = max(0, i - width), min(len(p), i + len(word) + width)
        text = ("..." if a > 0 else "") + p[a:i] + "«" + word + "»" + p[i + len(word):b] + \
            ("..." if b < len(p) else "")
        out_rows.append((lab, text))
    return out_rows


SCAN_TASK = """# SCAN TASK - words that might be stand-ins

Web novels sometimes use an innocent word in place of a rude or taboo one: a herb name that
sounds like a crude word (牛至 for 牛子), or a cute doubled word (牛牛). Translated literally,
such a word reads fine but makes nonsense ("the oregano on his arm"). Below are {n} words from
this book, each with examples from different parts of the book. Decide what each one means
**in this book**.

## How to decide
- **Literal is the default.** Most words mean exactly what they say. Say "stand-in" only when
  at least two examples make no sense if read literally, and make sense with the other meaning.
- The same word can be a stand-in in one book and literal in another. A 牛牛 can be a calf or a
  child's nickname; 小兄弟 is usually just "a young man"; 开车 is usually just driving. The
  "shared table says" note is only a hint about what the word *can* mean.
- A doubled word used as a pet name, a person's nickname or a sound is literal.
- A well-known fixed meme or phrase (一万只草泥马奔腾而过) can be decided from one clear example.
- «» marks a plain text match. Sometimes it straddles two words (拉«开车»门 = 拉开 + 车门,
  召«开开»学 = 召开 + 开学): ignore those examples and judge from the rest.
- A word that is simply crude or vulgar (not standing in for anything) is **vulgar**: it needs
  crude English, not a literal one.
- Your verdict applies to the whole book. If a word is literal almost everywhere but you see a
  real stand-in use too, say **unsure** and describe both.
- Confidence: **high** only if the examples clearly point one way. Otherwise **low**: a person
  will look at it. Never guess high to be helpful; a wrong "stand-in" spoils every later
  passage where the word is meant normally.

## What to write
Write one line per word into `work/scan_result.md`, nothing else:

    VERDICT: 词 | stand-in | high | what it stands for | tone | suggested English | how to handle | literal English to avoid (comma-separated)
    VERDICT: 词 | literal | high | what it means here (e.g. a young man; a calf named 牛牛)
    VERDICT: 词 | vulgar | high | what it means | tone | suggested English | how to handle | literal English to avoid
    VERDICT: 词 | unsure | low | why (what the examples suggest)

A stand-in line may also use low confidence. Write the English parts in English.
Example lines:

    VERDICT: 牛至 | stand-in | high | stand-in for 牛子 (penis); the herb name is the joke | deadpan, crude | his johnson | same English every time | oregano
    VERDICT: 小兄弟 | literal | high | "young man", a friendly form of address

Then run: `{cmd} scan-apply`

## Words
{words}
"""


def scan_task_ja(body):
    """The scan task for a Japanese book: suggestions and words to avoid are Japanese."""
    swaps = [
        ('("the oregano on his arm")', '(「腕にオレガノが」)'),
        ("it needs\n  crude English, not a literal one.", "it needs\n  crude Japanese, not a literal one."),
        ("tone | suggested English | how to handle | literal English to avoid (comma-separated)",
         "tone | suggested Japanese | how to handle | literal Japanese to avoid (comma-separated)"),
        ("tone | suggested English | how to handle | literal English to avoid\n",
         "tone | suggested Japanese | how to handle | literal Japanese to avoid\n"),
        ("Write the English parts in English.",
         "Write the meaning and notes in English or Chinese, the suggested wording and the words "
         "to avoid in Japanese."),
        ("| deadpan, crude | his johnson | same English every time | oregano",
         "| deadpan, crude | ムスコ | same word every time | オレガノ"),
    ]
    for a, b in swaps:
        body = body.replace(a, b)
    return body


def cmd_scan(args):
    book = workspace_from_args(args)
    paras = book_paragraphs(book)
    text = "\n".join(p for _, p in paras)
    known = set()
    for r in book.glossary():
        known.update(variants(r.get("zh")))
    for r in book.characters():
        known.update(variants(r.get("zh"), r.get("aliases")))
    extra = {r.get("term") for r in read_tsv(book.bible / "slang_extra.tsv")}
    decided = set(scan_done(book)) | extra | book.slang_off()
    shared = read_tsv(SKILL_DIR / "slang" / "zh_internet_slang.tsv")
    shared_terms = {r.get("term") for r in shared}
    cands = []
    for r in shared:
        t = r.get("term", "")
        if t in decided or t not in text:
            continue
        if "stand-in" in (r.get("tone") or "") or "ONLY" in (r.get("strategy") or ""):
            cands.append((t, text.count(t), "shared table says it can mean: " + r.get("meaning", "")))
    for w, n, noun in doubled_candidates(text, known | decided | shared_terms, limit=args.max_words):
        if noun >= 0.2:
            cands.append((w, n, "doubled word, used like a noun"))
    cands = cands[: args.max_words]
    if not cands:
        out("Nothing new to scan: every suspicious word has been decided.")
        nxt(next_action(book))
        return
    blocks = []
    for i, (w, n, why) in enumerate(cands, 1):
        ex = spread_examples(paras, w, args.examples)
        lines = ["### W%d  %s  (%d times; %s)" % (i, w, n, why)]
        lines += ["- E%d (%s): %s" % (j, lab, t) for j, (lab, t) in enumerate(ex, 1)]
        blocks.append("\n".join(lines))
    body = SCAN_TASK.format(n=len(cands), cmd=py_cmd(), words="\n\n".join(blocks))
    if book.lang == "ja":
        body = scan_task_ja(body)
    book.work.mkdir(exist_ok=True)
    (book.work / "scan_task.md").write_text(show_paths(body), encoding="utf-8")
    (book.work / "scan_result.md").write_text("", encoding="utf-8")
    book.cfg["scan"] = [w for w, _, _ in cands]
    book.save()
    out("Scan task written with %d word(s): %s" % (len(cands), ", ".join(w for w, _, _ in cands)))
    out("Task file: " + str(book.work / "scan_task.md"))
    nxt("Read work/scan_task.md, write one VERDICT line per word to work/scan_result.md, then run `"
        + py_cmd() + " scan-apply`.")


def cmd_scan_apply(args):
    book = workspace_from_args(args)
    words = book.cfg.get("scan") or []
    if not words:
        fail("No scan is open.", "Run `" + py_cmd() + " scan`.")
    path = book.work / "scan_result.md"
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    verdicts, problems = {}, []
    for raw in text.splitlines():
        line = raw.strip().lstrip("-*").strip()
        if not line.upper().startswith("VERDICT:"):
            continue
        f = [x.strip() for x in line.split(":", 1)[1].split("|")]
        if len(f) < 4:
            problems.append("Too few fields: " + line)
            continue
        term, kind, conf = f[0], f[1].lower(), f[2].lower()
        if term not in words:
            problems.append("Not one of the scanned words: " + term)
            continue
        if kind not in ("stand-in", "vulgar", "literal", "unsure") or conf not in ("high", "low"):
            problems.append("Use stand-in/vulgar/literal/unsure and high/low: " + line)
            continue
        bad_word = (has_cjk(f[5]) if book.lang == "en" else
                    bool(leftover_chinese(f[5], book.lang, book.keep_chars())[0])) if len(f) > 5 else True
        if kind in ("stand-in", "vulgar") and (len(f) < 6 or not f[5] or bad_word):
            problems.append("A " + kind + " line needs: meaning | tone | " + book.lname +
                            " suggestion | how to handle | literal words to avoid: " + line)
            continue
        verdicts[term] = f
    missing = [w for w in words if w not in verdicts]
    if problems or missing:
        for p in problems:
            out("ERROR: " + p)
        if missing:
            out("ERROR: No verdict yet for: " + ", ".join(missing))
        nxt("Fix work/scan_result.md and run `" + py_cmd() + " scan-apply` again.")
        sys.exit(1)
    shared_terms = {r.get("term") for r in read_tsv(SKILL_DIR / "slang" / "zh_internet_slang.tsv")}
    slang_rows, off_terms, flags, done_rows = [], [], [], []
    summary = {"stand-in": [], "vulgar": [], "literal": [], "check": []}
    for w in words:
        f = verdicts[w] + [""] * 8
        kind, conf = f[1].lower(), f[2].lower()
        if kind in ("stand-in", "vulgar") and conf == "high":
            tone = f[4] if kind == "stand-in" else ("vulgar" + (", " + f[4] if f[4] else ""))
            slang_rows.append({"term": w, "meaning": f[3], "tone": tone, "default_en": f[5],
                               "strategy": f[6], "avoid": f[7]})
            summary[kind].append(w)
        elif kind == "literal" and conf == "high":
            if w in shared_terms:
                off_terms.append(w)
            summary["literal"].append(w)
        else:
            flags.append({"chunk": "scan", "chapter": "", "para": w,
                          "note": "%s (%s confidence): %s" % (kind, conf, " | ".join(x for x in f[3:8] if x))})
            summary["check"].append(w)
        done_rows.append({"term": w, "verdict": kind, "confidence": conf,
                          "note": " | ".join(x for x in f[3:8] if x)})
    for line in merge_slang(book, slang_rows) + merge_noslang(book, off_terms):
        out(line)
    old = [r for r in read_tsv(book.bible / "scan_done.tsv") if r.get("term") not in words]
    write_tsv(book.bible / "scan_done.tsv", SCAN_DONE_HEADER, old + done_rows,
              ["Words the scan has decided. Delete a line to have it scanned again."])
    if flags:
        rows = read_tsv(book.bible / "flags.tsv") + flags
        write_tsv(book.bible / "flags.tsv", ["chunk", "chapter", "para", "note"], rows,
                  ["Places the translator was unsure about. Show these to the user."])
    book.cfg["scan"] = None
    book.save()
    out("Stand-in (added to the slang list): " + (", ".join(summary["stand-in"]) or "none"))
    out("Vulgar (added to the slang list as crude words): " + (", ".join(summary["vulgar"]) or "none"))
    plain = [w for w in summary["literal"] if w not in off_terms]
    out("Literal: " + (", ".join(plain) or "none"))
    if off_terms:
        out("Literal, and the shared slang hint is switched off for the whole book: "
            + ", ".join(off_terms) + "  (undo: delete the line from bible/slang_off.txt)")
    out("For the user to check (saved as flags): " + (", ".join(summary["check"]) or "none"))
    nxt("Show the user these three lists, with the examples for the 'check' words from "
        "work/scan_task.md, and ask what each means (if the user is not there, carry on: the "
        "'check' words stay saved as flags for later). Record their answers as SLANG: or NOSLANG: "
        "lines and run `" + py_cmd() + " add <file>`. Run `" + py_cmd() + " scan` again to see "
        "whether more words are waiting; when it says nothing new, " + next_action(book))


def cmd_flags(args):
    book = workspace_from_args(args)
    rows = read_tsv(book.bible / "flags.tsv")
    if not rows:
        out("No flags.")
    for r in rows:
        out("passage %s (%s) %s: %s" % (r.get("chunk"), r.get("chapter"), r.get("para"),
                                                 r.get("note")))
    nxt("Show these to the user. Fix any with `" + py_cmd() + " redo <passage>`; "
        "remove handled lines from bible/flags.tsv.")


def cmd_skip(args, value=True):
    book = workspace_from_args(args)
    by_n = {str(ch["n"]): ch for ch in book.cfg["chapters"]}
    for n in args.chapters:
        ch = by_n.get(str(n))
        if not ch:
            fail("No chapter %s. Run `%s status` or look at the list printed by init." % (n, py_cmd()))
        if value and book.cfg.get("current") in ch["chunks"]:
            fail("Chapter %s has an open passage. Accept it first." % n)
        ch["skip"] = value
        out("Chapter %s (%s): %s" % (n, ch["title"] or "no title",
                                      "left out" if value else "included again"))
    book.save()
    nxt(next_action(book))


def cmd_unskip(args):
    cmd_skip(args, value=False)


def cmd_redo(args):
    book = workspace_from_args(args)
    cid = "%04d" % int(args.passage)
    if cid not in book.chunk_ids():
        fail("No passage " + cid)
    if book.cfg.get("current") and book.cfg["current"] != cid:
        fail("Finish the open passage %s first." % book.cfg["current"])
    done = book.done()
    done.discard(cid)
    book.cfg["done"] = sorted(done)
    write_task(book, cid)
    book.cfg["current"] = cid
    book.cfg["stage"] = "translate"
    book.save()
    out("Passage %s reopened. The old translation stays in translated/%s.md until you accept "
        "a new one." % (cid, cid))
    nxt("Read work/current_task.md and translate it again, then `" + py_cmd() + " check`.")


# ------------------------------------------------------------------ build

def collect_chapters(book):
    done = book.done()
    chapters = []
    for ch in book.cfg["chapters"]:
        if ch.get("skip"):
            continue
        paras = []
        title = ""
        complete = True
        for cid in ch["chunks"]:
            if cid not in done or not book.tr_path(cid).exists():
                complete = False
                break
            blocks, _ = parse_output(book.tr_path(cid).read_text(encoding="utf-8"))
            for m, t in blocks:
                if m == "T":
                    title = t
                else:
                    paras.append(t)
        if paras:
            if ch.get("front"):
                title = title or book_words(book)["front"]
            chapters.append({"n": ch["n"], "title": title or book_words(book)["chapter"] % ch["n"],
                             "paras": paras, "complete": complete,
                             "front": bool(ch.get("front"))})
        if not complete:
            break
    return chapters


NOTICE = ("Unofficial AI-assisted translation made for the reader's own private use. "
          "All rights belong to the original author. Please do not share or publish it, "
          "and support the author through official releases where available.")

# Words the finished book shows to the reader, per target language.
BOOK_WORDS = {
    "en": {"notice": NOTICE, "chapter": "Chapter %d", "front": "Title Page",
           "contents": "Contents", "unfinished": "(translation of this chapter is not finished yet)",
           "author": "Unknown",
           "font": "font-family:Georgia,'Times New Roman',serif;",
           "head_font": "font-family:Helvetica,Arial,sans-serif;"},
    "ja": {"notice": "読者個人で楽しむために作られた、非公式のAI翻訳です。著作権はすべて原作者に"
                     "帰属します。共有・公開はしないでください。正規版がある場合は、そちらで作者を"
                     "応援してください。",
           "chapter": "第%d章", "front": "扉", "contents": "目次",
           "unfinished": "（この章の翻訳はまだ終わっていません）", "author": "不明",
           "font": "font-family:'Hiragino Mincho ProN','Yu Mincho','Noto Serif JP',serif;",
           "head_font": "font-family:'Hiragino Kaku Gothic ProN','Yu Gothic','Noto Sans JP',sans-serif;"},
}


def book_words(book):
    return BOOK_WORDS.get(book.lang, BOOK_WORDS["en"])


def book_css(book):
    w = book_words(book)
    return CSS.replace("font-family:Georgia,'Times New Roman',serif;", w["font"]) \
              .replace("font-family:Helvetica,Arial,sans-serif;", w["head_font"])


def esc(s):
    return html.escape(s, quote=True)


def build_md(book, chapters, path):
    title = book.cfg.get("title_en") or book.cfg["title"]
    w = book_words(book)
    lines = ["# " + title, "", "_" + w["notice"] + "_", ""]
    for ch in chapters:
        lines += ["", "## " + ch["title"], ""]
        for p in ch["paras"]:
            lines += [p, ""]
        if not ch["complete"]:
            lines += ["_" + w["unfinished"] + "_", ""]
    path.write_text("\n".join(lines), encoding="utf-8")


CSS = """body{font-family:Georgia,'Times New Roman',serif;line-height:1.6;margin:0 auto;max-width:40em;padding:1em;}
h1,h2{font-family:Helvetica,Arial,sans-serif;line-height:1.25;}
p{margin:0 0 .9em 0;text-indent:0;}
.notice{font-size:.85em;color:#666;border-left:3px solid #ccc;padding-left:.8em;}
"""


def build_html(book, chapters, path):
    title = book.cfg.get("title_en") or book.cfg["title"]
    w = book_words(book)
    parts = ["<!doctype html><html lang='%s'><head><meta charset='utf-8'>" % book.lang,
             "<meta name='viewport' content='width=device-width,initial-scale=1'>",
             "<title>%s</title><style>%s</style></head><body>" % (esc(title), book_css(book)),
             "<h1>%s</h1><p class='notice'>%s</p>" % (esc(title), esc(w["notice"])), "<nav><ol>"]
    for ch in chapters:
        parts.append("<li><a href='#c%d'>%s</a></li>" % (ch["n"], esc(ch["title"])))
    parts.append("</ol></nav>")
    for ch in chapters:
        parts.append("<h2 id='c%d'>%s</h2>" % (ch["n"], esc(ch["title"])))
        for p in ch["paras"]:
            parts.append("<p>%s</p>" % esc(p))
        if not ch["complete"]:
            parts.append("<p><em>%s</em></p>" % esc(w["unfinished"]))
    parts.append("</body></html>")
    path.write_text("\n".join(parts), encoding="utf-8")


def build_epub(book, chapters, path):
    title = book.cfg.get("title_en") or book.cfg["title"]
    w = book_words(book)
    lang = book.lang
    author = book.cfg.get("author_en") or w["author"]
    book_id = "urn:uuid:" + str(uuid.uuid5(uuid.NAMESPACE_URL, book.cfg["source_file"]))
    modified = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    def xhtml(t, body):
        return ("<?xml version='1.0' encoding='utf-8'?>\n<!DOCTYPE html>\n"
                "<html xmlns='http://www.w3.org/1999/xhtml' xmlns:epub='http://www.idpf.org/2007/ops' "
                "lang='%s' xml:lang='%s'><head><meta charset='utf-8'/><title>%s</title>"
                "<link rel='stylesheet' type='text/css' href='style.css'/></head><body>%s</body></html>"
                % (lang, lang, esc(t), body))

    files = {}
    files["OEBPS/style.css"] = book_css(book)
    files["OEBPS/title.xhtml"] = xhtml(title, "<h1>%s</h1><p class='notice'>%s</p>"
                                       % (esc(title), esc(w["notice"])))
    for ch in chapters:
        body = "<h2>%s</h2>" % esc(ch["title"])
        body += "".join("<p>%s</p>" % esc(p) for p in ch["paras"])
        if not ch["complete"]:
            body += "<p><em>%s</em></p>" % esc(w["unfinished"])
        files["OEBPS/c%04d.xhtml" % ch["n"]] = xhtml(ch["title"], body)
    nav = "<nav epub:type='toc' id='toc'><h1>%s</h1><ol>" % esc(w["contents"])
    nav += "".join("<li><a href='c%04d.xhtml'>%s</a></li>" % (ch["n"], esc(ch["title"]))
                   for ch in chapters)
    nav += "</ol></nav>"
    files["OEBPS/nav.xhtml"] = xhtml(w["contents"], nav)
    ncx = ["<?xml version='1.0' encoding='utf-8'?>",
           "<ncx xmlns='http://www.daisy.org/z3986/2005/ncx/' version='2005-1'><head>",
           "<meta name='dtb:uid' content='%s'/></head><docTitle><text>%s</text></docTitle><navMap>"
           % (book_id, esc(title))]
    for i, ch in enumerate(chapters, 1):
        ncx.append("<navPoint id='n%d' playOrder='%d'><navLabel><text>%s</text></navLabel>"
                   "<content src='c%04d.xhtml'/></navPoint>" % (i, i, esc(ch["title"]), ch["n"]))
    ncx.append("</navMap></ncx>")
    files["OEBPS/toc.ncx"] = "\n".join(ncx)
    manifest = ["<item id='css' href='style.css' media-type='text/css'/>",
                "<item id='nav' href='nav.xhtml' media-type='application/xhtml+xml' properties='nav'/>",
                "<item id='ncx' href='toc.ncx' media-type='application/x-dtbncx+xml'/>",
                "<item id='title' href='title.xhtml' media-type='application/xhtml+xml'/>"]
    spine = ["<itemref idref='title'/>"]
    for ch in chapters:
        manifest.append("<item id='c%04d' href='c%04d.xhtml' media-type='application/xhtml+xml'/>"
                        % (ch["n"], ch["n"]))
        spine.append("<itemref idref='c%04d'/>" % ch["n"])
    files["OEBPS/content.opf"] = (
        "<?xml version='1.0' encoding='utf-8'?>\n"
        "<package xmlns='http://www.idpf.org/2007/opf' version='3.0' unique-identifier='bookid'>"
        "<metadata xmlns:dc='http://purl.org/dc/elements/1.1/'>"
        "<dc:identifier id='bookid'>%s</dc:identifier><dc:title>%s</dc:title>"
        "<dc:creator>%s</dc:creator><dc:language>%s</dc:language>"
        "<meta property='dcterms:modified'>%s</meta></metadata>"
        "<manifest>%s</manifest><spine toc='ncx'>%s</spine></package>"
        % (book_id, esc(title), esc(author), lang, modified, "".join(manifest), "".join(spine)))
    container = ("<?xml version='1.0' encoding='utf-8'?>\n"
                 "<container version='1.0' xmlns='urn:oasis:names:tc:opendocument:xmlns:container'>"
                 "<rootfiles><rootfile full-path='OEBPS/content.opf' "
                 "media-type='application/oebps-package+xml'/></rootfiles></container>")
    with zipfile.ZipFile(path, "w") as z:
        z.writestr(zipfile.ZipInfo("mimetype"), "application/epub+zip",
                   compress_type=zipfile.ZIP_STORED)
        z.writestr("META-INF/container.xml", container, compress_type=zipfile.ZIP_DEFLATED)
        for name, data in files.items():
            z.writestr(name, data, compress_type=zipfile.ZIP_DEFLATED)


def cmd_build(args):
    book = workspace_from_args(args)
    chapters = collect_chapters(book)
    if not chapters:
        fail("Nothing is translated yet.", "Run `" + py_cmd() + " next`.")
    formats = [f.strip() for f in args.formats.split(",") if f.strip()]
    stem = slugify(book.ws.name)
    if not stem.endswith("-" + book.lang):
        stem += "-" + book.lang
    outdir = book.ws / "output"
    outdir.mkdir(exist_ok=True)
    made = []
    if "md" in formats:
        build_md(book, chapters, outdir / (stem + ".md"))
        made.append(outdir / (stem + ".md"))
    if "html" in formats:
        build_html(book, chapters, outdir / (stem + ".html"))
        made.append(outdir / (stem + ".html"))
    if "epub" in formats:
        build_epub(book, chapters, outdir / (stem + ".epub"))
        made.append(outdir / (stem + ".epub"))
    complete = sum(1 for c in chapters if c["complete"])
    total_ch = sum(1 for ch in book.cfg["chapters"] if not ch.get("skip"))
    out("Built %d of %d chapter(s) (%d of them complete)." % (len(chapters), total_ch, complete))
    for p in made:
        out("  " + str(p))
    nxt("Give the user these files. The .epub opens in Apple Books, Google Play Books, "
        "Calibre, or Kindle (via Send to Kindle).")


# ------------------------------------------------------------------- main

def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    ap = argparse.ArgumentParser(prog="novel.py", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("-w", "--workspace", help="workspace folder (default: the current book)")
    ap.add_argument("--version", action="version", version="chinese-novel-translator " + VERSION)
    sub = ap.add_subparsers(dest="cmd")

    p = sub.add_parser("init", help="set up a book (.txt or .epub)")
    p.add_argument("book")
    p.add_argument("--genre", default="general", help="general | xianxia | urban | historical")
    p.add_argument("--lang", default="en", help="target language: en (English, default) | ja (Japanese)")
    p.add_argument("--chunk-chars", type=int, default=1500,
                   help="Chinese characters per passage (default 1500)")
    p.add_argument("--name", help="short folder name for this book")
    p.add_argument("--root", help="where to create novel-translations/ (default: here)")
    p.add_argument("--no-trial", action="store_true", help="skip the one-chapter trial stop")
    p.add_argument("--review", default="full", choices=["off", "spot", "full"],
                   help="review pass after each passage (default: full)")
    p.add_argument("--force", action="store_true", help="start over, deleting progress")
    p.set_defaults(func=cmd_init)

    p = sub.add_parser("candidates", help="list frequent words that may be names or terms")
    p.add_argument("--chapters", type=int, default=5)
    p.add_argument("--top", type=int, default=80)
    p.add_argument("--min-count", type=int, default=3)
    p.set_defaults(func=cmd_candidates)

    p = sub.add_parser("scan", help="let the model judge suspicious words (stand-ins) with examples from the whole book")
    p.add_argument("--max-words", type=int, default=30)
    p.add_argument("--examples", type=int, default=4)
    p.set_defaults(func=cmd_scan)

    sub.add_parser("scan-apply", help="apply the VERDICT lines from work/scan_result.md").set_defaults(func=cmd_scan_apply)

    p = sub.add_parser("add", help="add TERM:/CHAR: lines from a notes file to the bible")
    p.add_argument("file")
    p.set_defaults(func=cmd_add)

    p = sub.add_parser("next", help="open the next passage and write its task file")
    p.add_argument("--force", action="store_true", help="rebuild the open task file")
    p.set_defaults(func=cmd_next)

    sub.add_parser("check", help="check work/current_output.md").set_defaults(func=cmd_check)
    sub.add_parser("polish", help="turn the draft into a review task (meaning first, then style)").set_defaults(func=cmd_polish)
    sub.add_parser("review", help="same as polish").set_defaults(func=cmd_polish)

    p = sub.add_parser("accept", help="save the passage and its notes")
    p.add_argument("--stop", action="store_true", help="do not suggest continuing")
    p.set_defaults(func=cmd_accept)

    sub.add_parser("status", help="show progress").set_defaults(func=cmd_status)

    p = sub.add_parser("set", help="change a setting: " + ", ".join(SETTABLE))
    p.add_argument("key")
    p.add_argument("value")
    p.set_defaults(func=cmd_set)

    p = sub.add_parser("pin", help="save paragraphs as a style example for this book, e.g. pin 3 P4-P7")
    p.add_argument("passage")
    p.add_argument("paras")
    p.add_argument("--label", help="short name for the example, e.g. 'banter'")
    p.add_argument("--en", help="file with the reader's edited English ([[P..]] lines)")
    p.add_argument("--why", help="one line on what this example teaches")
    p.add_argument("--no-apply", action="store_true",
                   help="with --en: do not put the edited English into the finished passage")
    p.set_defaults(func=cmd_pin)

    sub.add_parser("flags", help="list places the translator was unsure about").set_defaults(func=cmd_flags)

    p = sub.add_parser("set-char", help="change a character's gender, note or nicknames, e.g. set-char 苏晴 gender female")
    p.add_argument("zh")
    p.add_argument("field")
    p.add_argument("value")
    p.set_defaults(func=cmd_set_char)

    p = sub.add_parser("rename", help='change a name on purpose, e.g. rename 县丞 "Assistant Magistrate"')
    p.add_argument("zh")
    p.add_argument("english")
    p.add_argument("--fix-done", action="store_true",
                   help="also swap the old English for the new in passages already translated")
    p.set_defaults(func=cmd_rename)

    p = sub.add_parser("skip", help="leave chapters out, e.g. skip 2 (a table of contents)")
    p.add_argument("chapters", nargs="+")
    p.set_defaults(func=cmd_skip)

    p = sub.add_parser("unskip", help="include left-out chapters again")
    p.add_argument("chapters", nargs="+")
    p.set_defaults(func=cmd_unskip)

    p = sub.add_parser("redo", help="translate a passage again, e.g. redo 12")
    p.add_argument("passage")
    p.set_defaults(func=cmd_redo)

    p = sub.add_parser("build", help="assemble the translated book")
    p.add_argument("--formats", default="md,html,epub")
    p.set_defaults(func=cmd_build)

    args = ap.parse_args()
    if not args.cmd:
        ap.print_help()
        return
    try:
        args.func(args)
    except BrokenPipeError:  # output piped into `head` etc.
        try:
            sys.stdout = open(os.devnull, "w")
        except Exception:
            pass


if __name__ == "__main__":
    main()
