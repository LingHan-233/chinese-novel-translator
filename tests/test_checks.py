"""Tests for the checks in scripts/novel.py (standard library only).

    python -m unittest tests/test_checks.py -v

The first groups call the checking functions directly. CheckFlowTest runs the real commands on a
small made-up book in a temporary folder, the way an agent would."""
import io
import json
import os
import re
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import novel  # noqa: E402


class EnglishNumbersTest(unittest.TestCase):
    def nums(self, text):
        return novel.en_numbers(text)

    # bugs found on 2026-11-07
    def test_dash_between_two_numbers(self):
        self.assertEqual(self.nums("one hundred—one hundred fifty"), {100, 150})
        self.assertEqual(self.nums("a hundred — a hundred and fifty"), {100, 150})
        self.assertEqual(self.nums("one hundred-one hundred fifty"), {100, 150})
        self.assertEqual(self.nums("one hundred – one hundred fifty"), {100, 150})

    def test_ratio_skips_the_whole_second_number(self):
        self.assertEqual(self.nums("one in a hundred thousand"), {1})
        self.assertEqual(self.nums("one in ten thousand"), {1})
        self.assertEqual(self.nums("one in a hundred"), {1})
        self.assertEqual(self.nums("eight in ten"), {8})

    def test_number_mismatch_cases_from_the_tests(self):
        self.assertEqual(novel.number_mismatch("一百——一百五十", "one hundred—one hundred fifty"), [])
        self.assertEqual(novel.number_mismatch("十万人里也未必能有一人",
                                               "not one in a hundred thousand"), [])

    # behaviour that must not change
    def test_unchanged(self):
        self.assertEqual(self.nums("twenty-one"), {21})
        self.assertEqual(self.nums("twenty-first"), {21})
        self.assertEqual(self.nums("ninety-nine days"), {99})
        self.assertEqual(self.nums("three hundred and five"), {305})
        self.assertEqual(self.nums("two or three"), {2, 3})
        self.assertEqual(self.nums("1,000 men and 3.5 days"), {1000, 3})
        self.assertEqual(self.nums("a thirty-three-year-old man"), {33})
        self.assertEqual(self.nums("a three-legged toad"), {3})
        self.assertEqual(self.nums("a well-known face"), set())

    def test_real_errors_still_found(self):
        self.assertEqual(novel.number_mismatch("他扫了三遍。", "He swept it ten times."), [10])
        self.assertEqual(novel.number_mismatch("九十九天", "ninety days"), [90])


class JapaneseNumbersTest(unittest.TestCase):
    """ja_numbers must read exactly as in v0.9.4."""
    EXPECTED = {
        "九十九日間の禁欲": {99}, "二の腕を指して": set(), "十数秒で": set(), "完璧な三枚肉": set(),
        "十中八九、問題は": set(), "十回掃いた": {10}, "三メートルの巨人": {3}, "三万の霊石": {30000},
        "第四百十八章": {418}, "二、三日したら": {3}, "20秒後": {20}, "一石二鳥だ": set(),
        "五、六メートルも": {6},
    }

    def test_unchanged(self):
        for text, want in self.EXPECTED.items():
            self.assertEqual(novel.ja_numbers(text), want, text)


class NameUsedTest(unittest.TestCase):
    def test_articles_and_plurals(self):
        self.assertTrue(novel.name_used("the antiquity pavilion", "an antiquity pavilion member"))
        self.assertTrue(novel.name_used("formations", "the formation lines glowed"))
        self.assertTrue(novel.name_used("formations", "the formation"))
        self.assertTrue(novel.name_used("spirit stone", "three spirit stones"))
        self.assertTrue(novel.name_used("glasses", "the glass broke"))

    def test_old_substring_rule_still_counts(self):
        self.assertTrue(novel.name_used("dao", "the daoist bowed"))

    def test_real_misses_still_found(self):
        self.assertFalse(novel.name_used("flying sword", "he drew a sword"))
        self.assertFalse(novel.name_used("vast sky domain", "the vast sky"))
        self.assertFalse(novel.name_used("lin fan", "linfan"))

    def test_japanese_is_plain_substring(self):
        self.assertTrue(novel.name_used("青雲宗", "青雲宗の山門", "ja"))
        self.assertFalse(novel.name_used("青雲宗", "青雲の山門", "ja"))


class StyleLintTest(unittest.TestCase):
    def test_blue_in_the_face(self):
        hits = [a for p, n, a in novel.STYLE_LINT if re.search(p, "He felt blue in the face.", re.I)]
        self.assertTrue(any("blue in the face" in a for a in hits))


BOOK = """测试之书
作者：测试

第1章 开始

金阳秋是宗门长老。曹长老管外门，弟子都叫他老曹。

林凡吃下一枚筑基丹，在洞府里坐了一夜。

师尊看了他一眼，没有说话。

老曹在门口喊了一声。

这一年，他终于筑基了。

众人笑得前仰后合，嘿嘿嘿个不停。

第2章 继续

林凡又扫了一遍台阶，怀里揣着一枚筑基丹。
"""

NOTES = """CHAR: 林凡 | Lin Fan | male | protagonist |
CHAR: 金阳秋 | Jin Yangqiu | male | elder | 师尊
CHAR: 曹长老 | Elder Cao | male | outer sect elder | 老曹
TERM: 筑基 | Foundation Establishment | realm |
TERM: 筑基丹 | Foundation Pill | item |
TERM: 洞府 | cave abode | place |
SLANG: 嘿嘿嘿 | a sinister cackle | villainous | heh heh heh | keep it menacing | hey hey hey
"""


class CheckFlowTest(unittest.TestCase):
    """Runs the real commands on a made-up book in a temporary folder."""

    def setUp(self):
        self.old_cwd = os.getcwd()
        self.dir = Path(tempfile.mkdtemp())
        os.chdir(self.dir)
        (self.dir / "book.txt").write_text(BOOK, encoding="utf-8")
        self.run_cmd("init", "book.txt", "--genre", "xianxia", "--no-trial", "--name", "t")
        (self.dir / "notes.md").write_text(NOTES, encoding="utf-8")
        self.run_cmd("add", "notes.md")
        self.ws = self.dir / "novel-translations" / "t"

    def tearDown(self):
        os.chdir(self.old_cwd)
        shutil.rmtree(self.dir, ignore_errors=True)

    def run_cmd(self, *args):
        buf = io.StringIO()
        old_argv = sys.argv
        sys.argv = ["novel.py"] + list(args)
        try:
            with redirect_stdout(buf):
                try:
                    novel.main()
                except SystemExit:
                    pass
        finally:
            sys.argv = old_argv
        return buf.getvalue()

    def cfg(self):
        return json.loads((self.ws / "book.json").read_text(encoding="utf-8"))

    def chapter_one(self):
        """Skip front matter, open the first real chapter and return its source."""
        for ch in self.cfg()["chapters"]:
            if ch.get("front"):
                self.run_cmd("skip", str(ch["n"]))
        self.run_cmd("next")
        cid = self.cfg()["current"]
        return json.loads((self.ws / "source" / (cid + ".json")).read_text(encoding="utf-8"))

    def write_output(self, src, lines):
        text = "[[T]] Chapter 1: The Start\n\n" + "\n\n".join(
            "[[P%d]] %s" % (i, lines.get(i, "Lin Fan swept the steps.")) for i in
            range(1, len(src["paras"]) + 1))
        (self.ws / "work" / "current_output.md").write_text(text, encoding="utf-8")

    def para_index(self, src, needle):
        return [i for i, p in enumerate(src["paras"], 1) if needle in p][0]

    def test_name_checks(self):
        src = self.chapter_one()
        lines = {
            self.para_index(src, "金阳秋"): "Jin Yangqiu is an elder. Elder Cao runs the outer "
                                            "sect; the disciples call him Old Cao.",
            self.para_index(src, "筑基丹"): "Lin Fan took a Foundation Pill and sat all night "
                                            "in his cave abode.",
            self.para_index(src, "师尊"): "Master gave him a look and said nothing.",
            self.para_index(src, "老曹在门口"): "Old Cao shouted at the door.",
            self.para_index(src, "终于筑基"): "That year he finally broke through.",
        }
        self.write_output(src, lines)
        out = self.run_cmd("check")
        # 筑基 also appears on its own and the English misses it: still reported
        self.assertIn("Name check: 筑基 should appear", out)
        # names that are present / only addressed by title are not reported
        self.assertNotIn("Name check: 筑基丹", out)
        self.assertNotIn("Jin Yangqiu'", out)
        self.assertNotIn("Elder Cao'", out)

    def test_term_only_inside_a_longer_term(self):
        src = self.chapter_one()
        lines = {self.para_index(src, "终于筑基"): "That year he finally reached Foundation "
                                                   "Establishment.",
                 self.para_index(src, "筑基丹"): "Lin Fan took a Foundation Pill and sat all "
                                                 "night in his cave abode.",
                 self.para_index(src, "金阳秋"): "Jin Yangqiu is an elder. Elder Cao runs the "
                                                 "outer sect."}
        self.write_output(src, lines)
        out = self.run_cmd("check")
        self.assertNotIn("Name check: 筑基", out)
        self.assertNotIn("Name check: 洞府", out)

    def test_pill_only(self):
        """Chapter 2 has 筑基 only inside 筑基丹: no request for 'Foundation Establishment'."""
        for ch in self.cfg()["chapters"]:
            if "继续" not in (ch.get("title") or ""):
                self.run_cmd("skip", str(ch["n"]))
        self.run_cmd("next")
        cid = self.cfg()["current"]
        src = json.loads((self.ws / "source" / (cid + ".json")).read_text(encoding="utf-8"))
        self.assertIn("筑基丹", src["paras"][0])
        (self.ws / "work" / "current_output.md").write_text(
            "[[T]] Chapter 2: Going On\n\n[[P1]] Lin Fan swept the steps again, a Foundation "
            "Pill tucked in his robe.", encoding="utf-8")
        _, warnings, _ = novel.run_checks(novel.Book(self.ws), cid)
        self.assertFalse([w for w in warnings if w.startswith("Name check")], warnings)
        # with the pill missing from the English, the pill is still reported
        (self.ws / "work" / "current_output.md").write_text(
            "[[T]] Chapter 2: Going On\n\n[[P1]] Lin Fan swept the steps again, a pill tucked "
            "in his robe.", encoding="utf-8")
        _, warnings, _ = novel.run_checks(novel.Book(self.ws), cid)
        names = [w for w in warnings if w.startswith("Name check")]
        self.assertEqual(len(names), 1, names)
        self.assertTrue(names[0].startswith("Name check: 筑基丹 should appear"), names)

    def test_title_only_alias(self):
        """金阳秋 has the alias 师尊, 曹长老 has 老曹: a passage with only those is not checked."""
        book = novel.Book(self.ws)
        text = "师尊看了他一眼，没有说话。\n老曹在门口喊了一声。"
        rows = novel.entries_in(text, book.characters())
        self.assertEqual(rows, [])

    def test_own_slang_review_block(self):
        src = self.chapter_one()
        self.write_output(src, {})
        self.run_cmd("check")
        self.run_cmd("review")
        task = (self.ws / "work" / "current_task.md").read_text(encoding="utf-8")
        self.assertIn("This book's own slang entries", task)
        self.assertIn("a sinister cackle", task)

    def test_build_reminds_about_the_title(self):
        src = self.chapter_one()
        self.write_output(src, {})
        self.run_cmd("check")
        (self.ws / "work" / "current_notes.md").write_text("SUMMARY: test.\n", encoding="utf-8")
        self.run_cmd("accept")
        out = self.run_cmd("build")
        self.assertIn("set title_en", out)
        self.run_cmd("set", "title_en", "The Test Book")
        out = self.run_cmd("build")
        self.assertNotIn("NOTE: the book title", out)


if __name__ == "__main__":
    unittest.main()
