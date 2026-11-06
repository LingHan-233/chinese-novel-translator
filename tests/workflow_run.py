"""Run the whole novel.py workflow with fake model output and record everything.

usage: python tests/workflow_run.py <skill_dir> <run_dir> <en|ja>

The run dir gets a copy of the skill (so the printed commands are the same for every version)
and a log/ folder with the output of every command and every task file the script wrote.
To make sure a change did not alter the English workflow, run it for the old and the new
version and compare (only the run-dir path should differ):

    git worktree add /tmp/old <last release tag or commit>
    python tests/workflow_run.py /tmp/old /tmp/run_old en
    python tests/workflow_run.py . /tmp/run_new en
    diff -r /tmp/run_old/log /tmp/run_new/log
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

skill, run, lang = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]
if run.exists():
    shutil.rmtree(run)
run.mkdir(parents=True)
shutil.copytree(skill, run / "skill", ignore=shutil.ignore_patterns(".git", "__pycache__"))
log = run / "log"
log.mkdir()
step = [0]


def nv(*a, ok=None):
    step[0] += 1
    r = subprocess.run([sys.executable, "skill/scripts/novel.py"] + list(a), cwd=run,
                       capture_output=True, text=True, encoding="utf-8")
    name = "%03d_%s" % (step[0], "_".join(re.sub(r"[^\w]", "", x)[:12] for x in a[:2]))
    (log / (name + ".out")).write_text("$ novel.py %s\nexit=%d\n%s%s" % (
        " ".join(a), r.returncode, r.stdout, r.stderr), encoding="utf-8")
    task = ws() / "work" / "current_task.md" if ws() else None
    if task and task.exists():
        (log / (name + ".task.md")).write_text(task.read_text(encoding="utf-8"), encoding="utf-8")
    return r


def ws():
    p = run / "novel-translations" / "CURRENT"
    return run / "novel-translations" / p.read_text(encoding="utf-8").strip() if p.exists() else None


def cfg():
    return json.loads((ws() / "book.json").read_text(encoding="utf-8"))


def wfile(name, text):
    (ws() / "work" / name).write_text(text, encoding="utf-8")


EN_FILL = ["Lin Fan swept the steps again.", "\"Three times,\" he said.",
           "Wang Gui snorted and walked off.", "The stone glowed for a moment.",
           "He didn't answer. Then he couldn't help but smile, a trace of a smile, a hint of doubt.",
           "Ten disciples came down the steps, and twenty more followed."]
JA_FILL = ["林凡はまた石段を掃いた。", "「三回です」と彼は言った。",
           "王貴は鼻を鳴らして去っていった。", "石が一瞬だけ光った。",
           "彼は答えなかった。十分に考えてから、ようやく口を開いた。",
           "十人の弟子が石段を下りてきて、さらに二十人が続いた。"]


def fake_output(src, bad=False):
    fill = JA_FILL if lang == "ja" else EN_FILL
    lines = []
    if src["part"] == 1 and src.get("title"):
        lines.append("[[T]] " + ("第一章 掃除の少年" if lang == "ja" else "Chapter One: The Sweeper"))
    for i, p in enumerate(src["paras"], 1):
        t = " ".join(fill[(i + k) % len(fill)] for k in range(1 + len(p) // 40))
        if bad and i == 2:
            t += (" 这们说" if lang == "en" else "他们说这个剑")  # leftover Chinese
        if bad and i == 3 and lang == "ja":
            t = "林凡没有说话，转身走了，台阶上的落叶又多了一层。"  # untranslated, no kana
        lines.append("[[P%d]] %s" % (i, t))
    return "\n\n".join(lines) + "\n"


def src_of(cid):
    return json.loads((ws() / "source" / (cid + ".json")).read_text(encoding="utf-8"))


extra = ["--lang", lang] if lang != "en" else []
nv("init", "skill/tests/sample_book.txt", "--genre", "xianxia", "--name", "sample", *extra)
nv("candidates")
nv("status")
if lang == "ja":
    notes = ("CHAR: 林凡 | 林凡 | male | protagonist\nCHAR: 王贵 | 王貴 | male | steward\n"
             "TERM: 青云宗 | 青雲宗 | sect | \nTERM: 外门执事 | 外門執事 | title | \n"
             "TERM: 杂役逆袭系统 | 雑役逆襲システム | system | \nCHAR: 苏晴 | 苏晴 | female | bad form\n"
             "SLANG: 牛至 | stand-in for 牛子 | crude | ムスコ | same every time | オレガノ\n"
             "NOSLANG: 小兄弟\n")
else:
    notes = ("CHAR: 林凡 | Lin Fan | male | protagonist\nCHAR: 王贵 | Wang Gui | male | steward\n"
             "TERM: 青云宗 | Azure Cloud Sect | sect | \nTERM: 外门执事 | Outer Sect Steward | title | \n"
             "TERM: 杂役逆袭系统 | Chore Comeback System | system | \nTERM: 道 | Dao | concept | single\n"
             "SLANG: 牛至 | stand-in for 牛子 | crude | his johnson | same every time | oregano\n"
             "NOSLANG: 小兄弟\n")
(ws() / "work" / "bible_notes.md").write_text(notes, encoding="utf-8")
nv("add", "work/bible_notes.md")
nv("scan")
words = cfg().get("scan") or []
if words:
    sugg = "ムスコ" if lang == "ja" else "his thing"
    res = []
    for i, w in enumerate(words):
        if i % 3 == 0:
            res.append("VERDICT: %s | stand-in | high | stands for something | crude | %s | same | literal" % (w, sugg))
        elif i % 3 == 1:
            res.append("VERDICT: %s | literal | high | just the word" % w)
        else:
            res.append("VERDICT: %s | unsure | low | unclear" % w)
    wfile("scan_result.md", "\n".join(res) + "\n")
    nv("scan-apply")
nv("scan")

n_done = 0
trial_done = False
for loop in range(40):
    r = nv("next")
    if "TRIAL FINISHED" in r.stdout:
        nv("build")
        nv("flags")
        nv("pin", "1", "P2-P4", "--why", "short lines")
        nv("set", "trial", "false")
        trial_done = True
        continue
    if "Every passage is translated" in r.stdout:
        break
    cid = cfg()["current"]
    src = src_of(cid)
    bad = n_done == 0
    wfile("current_output.md", fake_output(src, bad=bad))
    nv("check")
    if bad:
        wfile("current_output.md", fake_output(src))
        nv("check")
    if n_done == 1:
        nv("set", "review", "spot")
    if n_done == 2:
        nv("set", "review", "full")
    nv("review")
    wfile("current_output.md", fake_output(src))
    nv("check")
    note = "SUMMARY: Passage %s happened.\n" % cid
    if n_done == 1:
        note += ("TERM: 宗门大比 | " + ("宗門大比" if lang == "ja" else "Grand Sect Contest") + " | event | \n"
                 "FLAG: P2 | unsure about tone\n")
    wfile("current_notes.md", note)
    nv("accept")
    n_done += 1
    if n_done == 4:
        nv("status")
        nv("rename", "王贵", "王貴人" if lang == "ja" else "Steward Wang", "--fix-done")
        nv("set-char", "林凡", "note", "hero")
        nv("redo", "2")
        nv("next")  # still open
        src = src_of(cfg()["current"])
        wfile("current_output.md", fake_output(src))
        nv("check")
        nv("review")
        nv("check")
        wfile("current_notes.md", "SUMMARY: redone.\n")
        nv("accept")
nv("status")
nv("build")
if lang == "ja":
    nv("set", "keep_chars", "苏")
    nv("set", "lang", "en")
nv("set", "genre", "urban")
print("steps:", step[0], "passages:", n_done)
