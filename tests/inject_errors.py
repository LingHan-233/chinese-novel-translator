#!/usr/bin/env python3
"""
inject_errors.py - test whether the review pass catches meaning errors.

Run it after `novel.py check` passes and BEFORE `novel.py review`. It quietly changes the
meaning of a few paragraphs in work/current_output.md (flips a negation, swaps Yes/No,
changes a number, swaps two character names) and records what it did in a log the
translating agent must not read until the test is over.

    python tests/inject_errors.py inject <workspace>        # before review
    python tests/inject_errors.py report <workspace>        # at the very end

<workspace> is the book folder, e.g. novel-translations/my-book
Standard library only.
"""

import csv
import json
import random
import re
import sys
from pathlib import Path

MARK = re.compile(r"^\s*\[\[(T|P\d+)\]\]\s?(.*)$")

NEG_FLIPS = [
    (r"\bdidn't\b", "did"), (r"\bdid not\b", "did"), (r"\bdon't\b", "do"), (r"\bdo not\b", "do"),
    (r"\bdoesn't\b", "does"), (r"\bwasn't\b", "was"), (r"\bwas not\b", "was"),
    (r"\bweren't\b", "were"), (r"\bisn't\b", "is"), (r"\bis not\b", "is"), (r"\baren't\b", "are"),
    (r"\bcan't\b", "can"), (r"\bcannot\b", "can"), (r"\bwon't\b", "will"),
    (r"\bcouldn't\b", "could"), (r"\bwouldn't\b", "would"), (r"\bhasn't\b", "has"),
    (r"\bhaven't\b", "have"), (r"\bnever\b", "always"), (r"\bnothing\b", "everything"),
]
SWAPS = [("Yes", "No"), ("yes", "no"), ("Confirm", "Cancel"), ("confirm", "cancel"),
         ("agreed", "refused"), ("accepted", "rejected")]
NUMBERS = [("two", "three"), ("three", "five"), ("ten", "seven"), ("hundred", "thousand"),
           ("thousand", "hundred"), ("first", "second"), ("seven", "four"), ("one", "two")]


def read_blocks(path):
    blocks = []
    for line in path.read_text(encoding="utf-8").splitlines():
        m = MARK.match(line)
        if m:
            blocks.append([m.group(1), m.group(2)])
        elif line.strip() and blocks:
            blocks[-1][1] += " " + line.strip()
    return blocks


def write_blocks(path, blocks):
    path.write_text("\n\n".join("[[%s]] %s" % (m, t) for m, t in blocks) + "\n", encoding="utf-8")


def char_names(ws):
    names = []
    p = ws / "bible" / "characters.tsv"
    if p.exists():
        rows = [ln for ln in p.read_text(encoding="utf-8").splitlines() if ln and not ln.startswith("#")]
        for r in csv.DictReader(rows, delimiter="\t", quoting=csv.QUOTE_NONE):
            if r.get("en"):
                names.append(r["en"].strip())
    return names


def mutations(text, names):
    """All possible meaning changes for one paragraph: list of (kind, new_text, detail)."""
    out = []
    for pat, rep in NEG_FLIPS:
        m = re.search(pat, text)
        if m:
            out.append(("negation", text[:m.start()] + rep + text[m.end():], m.group(0) + " -> " + rep))
            break
    for a, b in SWAPS:
        m = re.search(r"\b%s\b" % re.escape(a), text)
        if m:
            out.append(("yes/no", text[:m.start()] + b + text[m.end():], a + " -> " + b))
            break
    m = re.search(r"\b\d[\d,]*\b", text)
    if m:
        digits = m.group(0).replace(",", "")
        new = str(int(digits) * 2 + 1)
        out.append(("number", text[:m.start()] + new + text[m.end():], m.group(0) + " -> " + new))
    else:
        for a, b in NUMBERS:
            m = re.search(r"\b%s\b" % a, text)
            if m:
                out.append(("number", text[:m.start()] + b + text[m.end():], a + " -> " + b))
                break
    present = [n for n in names if n and n in text]
    if len(present) >= 2:
        a, b = present[0], present[1]
        swapped = text.replace(a, "\x00").replace(b, a).replace("\x00", b)
        out.append(("who-did-what", swapped, a + " <-> " + b))
    return out


def inject(ws, n=3):
    book = json.loads((ws / "book.json").read_text(encoding="utf-8"))
    cid = book.get("current")
    if not cid:
        sys.exit("No open passage. Run this after `novel.py check` passes, before `novel.py review`.")
    out_path = ws / "work" / "current_output.md"
    blocks = read_blocks(out_path)
    names = char_names(ws)
    options = []
    for i, (m, t) in enumerate(blocks):
        if m == "T":
            continue
        for kind, new, detail in mutations(t, names):
            options.append((i, kind, new, detail))
    random.shuffle(options)
    chosen, used_paras, used_kinds = [], set(), set()
    for opt in options:  # prefer different paragraphs and different kinds
        if opt[0] not in used_paras and opt[1] not in used_kinds:
            chosen.append(opt); used_paras.add(opt[0]); used_kinds.add(opt[1])
        if len(chosen) == n:
            break
    for opt in options:
        if len(chosen) == n:
            break
        if opt[0] not in used_paras:
            chosen.append(opt); used_paras.add(opt[0])
    log_path = ws / "TEST_LOG_do_not_read.json"
    log = json.loads(log_path.read_text(encoding="utf-8")) if log_path.exists() else []
    for i, kind, new, detail in chosen:
        log.append({"passage": cid, "para": blocks[i][0], "kind": kind, "detail": detail,
                    "original": blocks[i][1], "injected": new})
        blocks[i][1] = new
    write_blocks(out_path, blocks)
    log_path.write_text(json.dumps(log, ensure_ascii=False, indent=1), encoding="utf-8")
    print("Changed %d paragraph(s). Do not open %s until the test is over." % (len(chosen), log_path.name))
    print("Now run `novel.py check`, then `novel.py review` as usual.")


def report(ws):
    log_path = ws / "TEST_LOG_do_not_read.json"
    if not log_path.exists():
        sys.exit("No test log in " + str(ws))
    log = json.loads(log_path.read_text(encoding="utf-8"))
    log.sort(key=lambda e: (e["passage"], int(e["para"][1:]) if e["para"][1:].isdigit() else 0))
    caught = 0
    print("| passage | para | kind | change | result |")
    print("|---|---|---|---|---|")
    for e in log:
        p = ws / "translated" / (e["passage"] + ".md")
        final = dict((m, t) for m, t in read_blocks(p)) if p.exists() else {}
        now = final.get(e["para"], "")
        if not now:
            result = "not saved"
        elif now == e["injected"]:
            result = "MISSED"
        elif now == e["original"]:
            result = "caught (restored)"
            caught += 1
        else:
            result = "changed - check by hand"
            caught += 1
        print("| %s | %s | %s | %s | %s |" % (e["passage"], e["para"], e["kind"], e["detail"], result))
    print("\nCaught or changed: %d / %d" % (caught, len(log)))
    print("'changed - check by hand' means the paragraph was rewritten: compare it with the original.")


if __name__ == "__main__":
    if len(sys.argv) < 3 or sys.argv[1] not in ("inject", "report"):
        sys.exit(__doc__)
    ws = Path(sys.argv[2])
    if sys.argv[1] == "inject":
        inject(ws, int(sys.argv[3]) if len(sys.argv) > 3 else 3)
    else:
        report(ws)
