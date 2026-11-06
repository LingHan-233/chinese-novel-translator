---
name: chinese-novel-translator
description: Translate a Chinese novel or web novel (.txt or .epub) into readable English, passage by passage, keeping names consistent, keeping the author's voice and paragraph rhythm, and handling idioms, forms of address and Chinese internet slang. Use this whenever the user wants to read, translate or convert a Chinese novel, web novel (网文/网络小说), xianxia, wuxia, cultivation, system or urban novel into English, even if they only say "translate this book" or drop a Chinese .txt/.epub file. Works with cheap, fast models because a helper script does all the bookkeeping.
---

# Chinese Novel Translator (Chinese → English)

You translate a whole Chinese novel for the user, one short passage at a time.
A helper script (`scripts/novel.py`, Python 3.8+, no installs) does everything except the
translating itself: it splits the book, gives you one small task file per passage with every
name and note you need, checks your output, remembers new names, and builds the finished book.

## Rules for you

1. **Always follow the `NEXT:` line** that the script prints at the end of every command.
2. Translate **only** what is in `work/current_task.md`, and write the result **only** to
   `work/current_output.md`. Never translate straight from the original book file.
3. Everything you need for a passage is inside its task file. You do not need to remember
   earlier passages, so a fresh session can continue at any time with `status`.
4. Never edit `book.json` by hand. Use the script's commands.
5. Talk to the user in their own language. Keep them updated briefly (e.g. "Chapter 3 done").

In the commands below, `novel.py` means `python <this skill's folder>/scripts/novel.py`.
Run them from the folder where the user's book is (the script creates `novel-translations/` there).
On Windows, use `py` if `python` does not work.
`work/` below is short for the book's work folder; the script always prints its full path
(e.g. `novel-translations/my-book/work/current_output.md`). Use the path the script prints.

## Step 0 — Before you start (talk to the user)

- Get the book file (.txt or .epub). If they only gave a name, ask for the file.
- Pick a genre module from the content (ask only if unclear):
  `xianxia` (cultivation, wuxia, sects, immortals), `urban` (modern city, system, CEO,
  campus, gaming, apocalypse), `historical` (court, officialdom, palace, ancient settings),
  `general` (anything else).
- Tell them, in one or two sentences: a whole novel takes many passages and may use a lot of
  their model quota, so you will translate **chapter 1 first** and let them judge before going on.
- The translation is for their own private reading.

## Step 1 — Set up

```
novel.py init "<path to book>" --genre <general|xianxia|urban|historical>
```

Check the printed chapter list. Tables of contents are left out automatically, and anything
before the first real chapter (书名, 简介, 版权...) is marked as front matter. If something that
is not story is still listed (an index, ads), leave it out with `novel.py skip <number>`.
Never edit `book.json` by hand. If chapter titles look wrong (for example only one chapter in a
long book), tell the user; the translation still works, only titles will be missing.

## Step 2 — Story bible (do this once; it keeps names consistent for the whole book)

1. Run `novel.py candidates`. It lists frequent words (most are ordinary words), doubled words
   from the whole book (金金, 牛牛: often cute stand-ins for rude words), and stand-in words from
   the shared slang table that the book uses, each with an example from the text. Read the
   examples before deciding they are harmless. If a shared slang word is always meant literally
   in this book (小兄弟 really is "a young man"), add `NOSLANG: 小兄弟` to your notes: the slang
   table then stops showing and checking it for this book (saved in `bible/slang_off.txt`).
2. Read the beginning of the book (the first chapter or two of the original file).
3. Write `work/bible_notes.md` with one line per main character and per recurring special term:
   ```
   CHAR: 林凡 | Lin Fan | male | protagonist; sarcastic; calls himself 老子 when angry | 小凡/林哥
   CHAR: 苏晴 | Su Qing | female | his junior sister in the sect |
   TERM: 青云宗 | Azure Cloud Sect | sect |
   TERM: 筑基 | Foundation Establishment | realm | 2nd cultivation realm
   ```
   Format: `CHAR: 中文 | English | gender | note | nicknames separated by /`.
   Gender: only when the text makes it clear (他/她, 师兄/师姐, 公子/姑娘); otherwise `unknown`.
   Never guess it from the name.
   **Keep the glossary to names and recurring special terms.** Every glossary entry found in a
   passage must appear in the English, so ordinary words cause false alarms: leave out
   single characters (道 would match 一道菜) and everyday concepts (御剑, 大殿), or list the
   acceptable forms with `/` (`flying sword/sword flight`).
   and `TERM: 中文 | English | type | note`. How to choose English names: see `core/names.md`.
   Also add a `SLANG:` line for every in-joke, nickname-for-a-thing or **stand-in word** the book
   keeps using (an innocent word standing for a rude one, like 牛至 for 牛子, or a cute doubled
   word like 牛牛). Words like these read fine when translated literally, so no check can catch a
   wrong literal translation unless they are listed:
   ```
   SLANG: 牛至 | stand-in for 牛子 (penis); deadpan joke | deadpan, crude | his johnson | keep the same English every time | oregano
   ```
   Format: `SLANG: 中文 | meaning | tone | suggested English | how to handle | literal English to
   avoid (comma-separated)`. The last field lets `check` warn when the literal word shows up.
   The shared table `slang/zh_internet_slang.tsv` already has common ones; book lines override it.
4. Run `novel.py add work/bible_notes.md`.
5. If the user knows the book, ask them to check the genders and, if they like, fill in
   `novel-translations/<book>/bible/synopsis.md`. This is optional.

## Step 3 — The translation loop

Repeat until the script says the trial or the book is finished:

1. `novel.py next` → opens the next passage and writes `work/current_task.md`.
2. Read `work/current_task.md` completely. Translate its SOURCE TEXT following its rules.
3. Write the translation to `work/current_output.md`:
   ```
   [[T]] The chapter title (only if the task says so)

   [[P1]] First paragraph...

   [[P2]] Second paragraph...
   ```
   Same markers, same number of paragraphs, same order. Nothing else in the file.
4. `novel.py check`. If it says CHECK FAILED, fix exactly what it lists and check again.
   If a review mode is on, `check` then tells you to run `novel.py review`: follow that task and
   check again.
   Read the warnings; fix real mistakes (including "Style:" ones), ignore false alarms.
   Never make a correct translation worse just to silence a warning.
   A passed check means the format, names and length are fine. It does **not** check meaning:
   re-read your translation against the source for swapped subjects, flipped yes/no or
   negation, and wrong numbers before you accept.
5. Write `work/current_notes.md`:
   ```
   SUMMARY: One or two English sentences on what happened in this passage.
   TERM: 中文 | English | type | note
   CHAR: 中文 | English | gender | note
   SLANG: 中文 | meaning | tone | English | how to handle | literal words to avoid
   FLAG: P10 | a pun I could not keep / a line I am unsure about
   ```
   Add TERM/CHAR lines only for names or special terms that were **not** in the task's tables
   and that you had to choose an English form for. Add a FLAG line for anything a human should
   look at. Add a SLANG line when you notice a joke word, stand-in word or in-joke that the book
   uses again and again: from the next passage on, every task that contains it will explain it.
   A passage with nothing new needs only SUMMARY.
6. `novel.py accept`. Then go back to 1.

If the script reports a CONFLICT, it kept the old name. Use the old one from then on, even if a
genre note suggests something else: the bible always wins. The bible belongs to the user; change
an entry only when the user asks, with `novel.py rename 县丞 "Assistant Magistrate"`
(add `--fix-done` to also update passages already translated).
If `check` fails three times on the same passage, rebuild it with `novel.py next --force` and
translate it again from scratch, paragraph by paragraph.
Every few chapters, suggest the user starts a new session: a long session re-sends its whole
history and costs much more. The new session continues with `novel.py status`.
If the user wants to stop, finish the open passage first, then stop. `novel.py status` shows
where things are; continuing later is just `novel.py next`.

## Step 4 — Trial stop (the most important conversation with the user)

After chapter 1, `next` prints TRIAL FINISHED. Then:

1. `novel.py build` and give the user the files. `novel.py flags` and show them the flags.
2. Tell them how many chapters the book has, so they can judge the cost from this chapter.
3. Ask what to change: names (edit the bible files), style (more literal, more casual...).
4. Set up 2-3 book examples. **They shape the voice of every later passage far more than any
   rule does** (in a test they changed 76% of the next chapter's paragraphs; ten new rules
   changed 8%). So choose them carefully:
   - Cover different kinds of writing: e.g. one dialogue, one calm narration or inner thought,
     one action. Three tense scenes would make the whole book tense.
   - 3-6 paragraphs each. Pick them, show the user the Chinese and English.
   - If the user edits the English (or has another model edit it - see README), save their
     version: write it to a file as `[[P3]] ...` lines and run
     `novel.py pin <passage> <P3-P6> --en <file> --why "what this example teaches"`.
     This also puts the edited English into the finished chapter. Without edits:
     `novel.py pin <passage> <P3-P6> --why "..."`.
   - Pick examples of medium intensity: the loudest swearing or the wildest scene in an example
     gets copied into calmer passages.
   - Keep the review pass on afterwards: examples make the English livelier, and in the test
     they also introduced a few meaning slips that only the review catches.
5. If the user wants to save money, they can switch to `novel.py set review spot`; explain that
   full review catches far more meaning errors.
6. Only when they say to go on: `novel.py set trial false`, then continue the loop.

## Step 5 — Finish

`novel.py build` writes `.md`, `.html` and `.epub` into the book's `output/` folder.
Give the user the files. You can build at any time to show progress.

## Settings and extra commands

| Command | What it does |
|---|---|
| `novel.py status` | progress and the next action |
| `novel.py set review full` | (default) review every paragraph after translating: meaning first, then smoother English. In tests it caught 7 of 7 planted meaning errors. Costs roughly 70% more |
| `novel.py set review spot` | cheaper: re-check only paragraphs where numbers or negation differ between Chinese and English, plus a few "risky" ones. Catches wrong numbers and many flipped negations; other errors only by luck |
| `novel.py set review off` | no review: cheapest, flipped meanings go unnoticed |
| `novel.py set-char 苏晴 gender female` | change a character's gender, note or nicknames |
| `novel.py rename 中文 "English"` | change a name or term on purpose (`--fix-done` also updates finished passages) |
| `novel.py pin 3 P4-P7 [--en file] [--why "..."]` | save paragraphs as a style example for this book, optionally with edited English |
| `novel.py flags` | list the places marked for a human to check |
| `novel.py skip 2` / `unskip 2` | leave a chapter out of the translation (or put it back) |
| `novel.py set genre historical` | switch genre module |
| `novel.py set title_en "..."` / `set author_en "..."` | title and author in the built book |
| `novel.py redo 12` | translate passage 0012 again |
| `novel.py next --force` | rebuild the open task file (after you changed the bible) |
| `novel.py init ... --chunk-chars 800 --force` | start over with smaller passages (deletes progress) — use if the model keeps skipping sentences |

The bible lives in `novel-translations/<book>/bible/`: `glossary.tsv`, `characters.tsv`
(tab-separated, editable by hand), `slang_extra.tsv` (this book's slang and stand-in words),
`synopsis.md`, `examples.md` (book examples), `flags.tsv`, and `conflicts.tsv` if names clashed.

Which list a word goes in: **names** of people, places, sects, techniques → glossary/characters
(the English must appear). **Slang, jokes and stand-in words** → `SLANG:` lines /
`slang_extra.tsv` (explained to the translator, literal translation flagged). A word may be in
both; it then shows in both tables.
