<!--
Japanese example pairs shown to the model when the target language is Japanese. All texts are written
for this project (no copyrighted novels). Each section starts with "## [tags] title". Tags: general,
xianxia, urban. The script picks up to two examples matching the book's genre plus general ones.
Keep the idiom example first: it is the general example every book gets.
DRAFT (v0.9.4): checked once by a second model (GLM); not yet by a Japanese reader.
-->

## [general] Chinese idioms and net phrases: say it the Japanese way
ZH:
[[P1]] 火烧眉毛了，他还在那儿慢悠悠地喝茶。
[[P2]] "你脑子进水了？这种合同也敢签！"
[[P3]] 王经理挤出一个比哭还难看的笑："那……走一步看一步吧。"
JA:
[[P1]] 尻に火がついているというのに、彼はのんびり茶をすすっている。
[[P2]] 「頭どうかしてるのか？　こんな契約によくサインできたな！」
[[P3]] 王部長は今にも泣き出しそうな顔で、引きつった笑みを浮かべた。「じゃあ……まあ、出たとこ勝負でいくか」
Why: each Chinese phrase becomes the Japanese phrase that does the same job. 火が眉毛まで, 頭に水が入る, 泣くより醜い笑み and 一歩進んでは一歩見る are word-for-word copies that no Japanese writer would use.

## [general] Short paragraphs, dropped subject, small talk
ZH:
[[P1]] 门开了。
[[P2]] 是她。
[[P3]] 周远站在门口，手里的伞还在滴水。看见屋里的人，愣了一下，又像什么都没发生似的，把伞靠在墙边。
[[P4]] "吃了吗？"
JA:
[[P1]] 扉が開いた。
[[P2]] 彼女だった。
[[P3]] 戸口には周遠が立っていた。手にした傘から、まだしずくが落ちている。部屋にいる相手を見て一瞬固まり、それから何事もなかったように、傘を壁に立てかけた。
[[P4]] 「メシ、食ったか？」
Why: one-line paragraphs stay one line; no 彼は is added where Japanese does not need it; the awkward everyday greeting stays awkward.

## [xianxia] Forms of address, realms, tone without 淡々と言った
ZH:
[[P1]] "师兄，"苏晴压低了声音，"那位前辈……似乎已是金丹境。"
[[P2]] 林凡没有回头，只是淡淡道："金丹又如何？"
JA:
[[P1]] 「師兄」蘇晴が声をひそめた。「あの先輩……もう金丹境に達しているみたいです」
[[P2]] 林凡は振り返りもしない。「金丹だから何だ？」
Why: titles and realms keep their kanji in Japanese form (师兄 → 師兄, 苏 → 蘇); 淡淡道 gets no tag at all: the calm is in the line.

## [xianxia] Arrogant self-reference, insults, counting
ZH:
[[P1]] "本座活了三千年，还轮不到你一个筑基小辈来教训！"
[[P2]] 话音未落，一道金光从他袖中射出，直取对方面门。
[[P3]] "找死！"
JA:
[[P1]] 「我は三千年を生きてきたのだ。築基ふぜいの小僧に説教される覚えはない！」
[[P2]] 言い終わらぬうちに、袖からひと筋の金光がほとばしり、相手の顔面へまっすぐ向かった。
[[P3]] 「死にたいらしいな！」
Why: 本座 becomes an imperious first person (我); 小辈 keeps its contempt (小僧); a beam of light is ひと筋 in Japanese, never 一道の; 找死 becomes the Japanese taunt, not a literal "seeking death".

## [urban] System panels, money, slang
ZH:
[[P1]] 【叮！检测到宿主遭受羞辱，打脸系统已激活。】
[[P2]] 【新手任务：让对方当众道歉。奖励：现金十万元。】
[[P3]] 陈阳愣住了。十万？他兜里现在只剩二十三块五。
[[P4]] 室友瘫在床上："摆烂吧，明天再说。"
JA:
[[P1]] 【ピコン！　宿主への侮辱を検知。ざまぁシステム、起動しました。】
[[P2]] 【初心者クエスト：相手に公衆の面前で謝罪させよ。報酬：現金十万元。】
[[P3]] 陳陽は固まった。十万？　ポケットには23.5元しか残っていない。
[[P4]] ルームメイトはベッドにぐったり寝転がっている。「もういいや。明日考えよう」
Why: panels read like a Japanese game (ピコン, クエスト); 打脸 becomes ざまぁ, the Japanese web-novel word for the same pleasure; money stays in yuan; 摆烂 becomes Japanese slang of the same strength, not an explanation.
