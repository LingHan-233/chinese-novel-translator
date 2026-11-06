# Chinese Novel Translator (v0.9.1)

Read Chinese web novels in English with your own AI agent.

Give your agent a Chinese novel (`.txt` or `.epub`). It translates the book passage by passage and hands you back an `.epub`, `.html` and `.md` you can read anywhere. Names stay consistent from chapter 1 to chapter 1000, the author's voice and paragraph rhythm are kept, and idioms, forms of address and internet slang are translated by what they mean instead of word by word.

[中文说明](README.zh-CN.md)

**New in v0.9.0 (testing):** translate into Japanese instead, with `init ... --lang ja`. Names and genre terms keep their kanji in Japanese form; the checks catch leftover Chinese characters. English is still the default and works exactly as before.

## Why it works with cheap models

Fast, low-cost models (the "flash" tier) translate well sentence by sentence but lose track over a long book. This project does not ask them to remember anything:

- A helper script splits the book into short passages and builds one small task file per passage. Each task file already contains the names, characters, slang and story context that passage needs.
- After each passage the script **checks the output**: missing or merged paragraphs, leftover Chinese, commentary, summarising instead of translating, names that drift. The model fixes what it lists before moving on.
- New names the model chooses are saved to a glossary and used in every later passage.
- Before translating, the model scans the whole book for **stand-in words** (an innocent word used for a rude one, like 牛至 for 牛子) using several examples of each, so these jokes are not translated literally. Literal is the default; uncertain words are left for you to decide.

The checks cover format and consistency, not meaning: a passed check does not prove a sentence was understood correctly. Two things raise quality the most:

- **Book examples.** After the first chapter, pick 2-3 short bits you like (or rewrite them). The agent saves them with `pin`, and every later passage imitates that voice.
- **The review pass** (on by default). After each passage the agent re-reads every paragraph against the Chinese, looking for meaning errors first (who did what to whom, flipped negation, yes/no, numbers, titles, lost jokes), then smoothing the English. In a test where errors were planted on purpose, it caught 7 of 7; with review off they all slipped through. It costs roughly 70% more. `set review spot` is a cheaper middle ground that reliably catches wrong numbers but little else.

A cheap model alone gives readable, mostly accurate, somewhat plain English.

## What you need

- An AI agent that can read and write files and run commands on your computer (a coding agent such as Claude Code, or a similar tool).
- Python 3.8 or newer. Nothing else to install.

## Install

Tell your agent:

> Download https://github.com/LingHan-233/chinese-novel-translator and install it as a skill. Then read its SKILL.md.

If your agent does not support skills, cloning the folder anywhere is enough: tell it to read `SKILL.md` and follow it.

## Use

> Translate `my-novel.txt` into English with the chinese-novel-translator skill.

The agent will set up the book, write a short list of the main characters and terms, translate **chapter 1 only**, and show it to you. Read it, ask for changes ("call him Old Wang, not Lao Wang", "less formal"), and tell it to continue when you are happy. You can stop at any time and continue later in a new session.

## Can't judge English? Let a second model edit the examples

The book examples matter most, but you don't need to write English to make good ones. After chapter 1, ask your agent for 2-3 short bits (one dialogue, one calm passage, one action), then open a chat with a **different** model (ideally a stronger one; it is only a few paragraphs) and paste them with this prompt:

> You are an experienced editor of Chinese web novels translated into English. Below are a few paragraphs: Chinese original and draft English, each with a marker like [[P1]]. Revise the English. (1) The meaning must match the Chinese exactly: nothing left out, nothing added, the same who-does-what, the same yes/no, the same numbers. (2) Faithful in meaning, **not word for word**: it should read like English fiction written in English, with no translationese. (3) Keep the original's tone: jokes stay funny, swearing stays swearing, keep its "!" and "?". (4) Keep names and terms exactly as in the draft. (5) Keep the markers and the number of paragraphs. Output two parts: first the revised English only, by marker; then, **in Chinese**, for each paragraph: what the English now says, and what you changed and why.

Check the second part: if its Chinese retelling matches the original, the meaning is right. Then give the English back to your agent and ask it to `pin` it with `--en`.

## Test results so far

Small tests on the first chapters of three web novels with a cheap model (DeepSeek V4.1 Flash):

- With meaning errors planted on purpose after translation, the full review caught 7 of 7. With a spot review that checked about a quarter of the paragraphs, 6 of 24.
- Three book examples edited by a second model changed 76% of the next chapter's paragraphs toward their voice (shorter, livelier sentences), compared with 8% from ten new rules. They also caused a few slips (a dropped exclamation, one phrase whose meaning flipped), which is why the review stays on by default.

These are small samples; treat them as a direction, not a guarantee.

## Cost

Each passage is about 1,500 Chinese characters plus about 2,500 tokens of instructions and context: roughly 4,000 tokens in and 1,500 out to translate it, and about another 3,000 in and 1,500 out for the default review. A 1,000,000-character web novel is about 670 passages. Agents also re-send their conversation history, which adds more, so **start a new session every few chapters** (the agent continues where it stopped). Check what chapter 1 cost you before committing to a whole book.

## Please read

This tool is for translating books **for your own private reading**. Do not post, share or sell the translations. If a book has an official English edition, read and support that one.

## What's inside

| Path | What it is |
|---|---|
| `SKILL.md` | Instructions for the agent |
| `scripts/novel.py` | The helper script: split, task files, checks, glossary, EPUB build |
| `core/` | Translation rules and how names are handled |
| `genres/` | Notes for xianxia/wuxia, urban/system, historical/court, and everything else |
| `lang/en/` | English style guide and example translations |
| `slang/zh_internet_slang.tsv` | Internet slang, web-novel jargon and stand-in words (谐音/委婉替代) with suggested English and literal translations to avoid |
| `templates/` | Empty glossary, character list and synopsis |
| `tests/sample_book.txt` | A short original sample novel to try the workflow |
| `tests/scan_sample_a.txt`, `tests/scan_sample_b.txt` | Two short original stories for testing the stand-in scan (the same words are literal in one and stand-ins in the other) |

## Acknowledgements

The design learned from two open-source translation projects: **AiNiee** (its glossary, character table and example-driven prompting) and **wenyi** by BigDawnGhost (the idea of giving the translator book-wide context). No code from either project is used here; this is an independent implementation built for agents and cheap models. If you need a desktop app with a full interface, AiNiee may suit you better.

## License

MIT, see [LICENSE](LICENSE). The license covers this tool, not the novels you translate with it.

## Contributing

The easiest and most useful contributions:

- **Slang**: add rows to `slang/zh_internet_slang.tsv` (term, meaning, tone, suggested English, how to handle, literal English to avoid). Stand-in words (an innocent word used for a rude one, like 牛至 for 牛子) are especially useful: a literal translation of them reads fine and slips past every other check.
- **Examples**: add short, original Chinese/English pairs to `lang/en/examples.md`. No text from published novels.
- **Genre notes**: improve `genres/*.md` or add a new genre (romance, historical, horror...).
