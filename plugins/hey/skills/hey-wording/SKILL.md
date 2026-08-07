---
name: hey-wording
description: How to word what you write around a hey card — shape, headings, tone, and the rule that the card is pasted verbatim. Read this when a hey skill tells you to, before writing prose above or below a card. Not a command; the other hey skills reference it.
---

# Writing around a card

Split out of `hey-ledger` because nine skills needed this one section and pulled three
hundred lines to get it. Everything here is about the prose that goes **around** the card;
the ledger's own format and the commands live in `hey-ledger`.

The card is the data. Everything you write around it is read by a person who is about to
start or finish a day's work, so it reads like a colleague talking, not like a report.

**Print the card before you write anything.** Script output is not visible to the user —
in most harnesses a tool result is shown to the model and not to the person. A card that
is only summarised is a card the user never saw. So paste the block verbatim, inside a
fenced code block, above your prose. Never paraphrase it into markdown headings, never
rebuild it as a table, never trim a section because it looks redundant. The box drawing,
the bar glyphs and the column alignment are the format; re-typing them by hand breaks
them. Your writing goes **under** the card, never in place of it.

**Shape.** At most three blocks. Each is a one-line heading and two to four bullets. One
closing sentence, and only if it says something the numbers do not.

**Headings are bold bracket labels, padded inside** — `**[ Pick up ]**`,
`**[ Today  8h = AI 1.0 ]**`, `**[ Blocked ]**` — never markdown headings. A `##` renders
as one more weight of bold in a terminal, which separates nothing next to a card built out
of box drawing. The brackets read as labels at a glance, the inner spaces keep the bracket
off the first word, and the bold carries the weight a heading would have given.

The asterisks are the markdown, not part of the label: what the reader sees is a bold
`[ Pick up ]`.

This holds for **every** block you write, not only the ones named in the examples. A
heading you invent for the occasion — `**[ Verified in code ]**`, `**[ What changed ]**` —
takes the same form.

**One divider, and only one.** A rule between the card and your prose marks where script
output ends and judgement begins. Do not put rules between the prose blocks — with three
blocks the labels already separate them, and more rules turn into the noise they were
meant to cut. Never draw a `─── heading ───` rule of your own: that is the card's shape,
and borrowing it blurs which lines a script produced.

```
🚧 막힌 것 6
   · 백엔드에 2xx 선언 추가 요청

────────────────────────────────────────────

**[ Pick up ]**
- lane-a-client-transport  keen-ios/client-transport
  The lane for today's item 1. Resume there

**[ Today  8h = AI 1.0 ]**
1. SamanthaClient transport      AI 0.5 (rough split)
2. codegen post-processing       AI 0.1 (rough split)
   AI 0.6 total. Item 3 skipped — its prerequisite is unfinished

**[ Blocked ]**
- Blocks item 1 today: X-Region undecided
- Someone else must clear: 2xx on 34 ops, code enum, prod host
```

**Words to drop.** These are the tells that something was generated rather than said:

- `살펴보겠습니다` `요약하면` `핵심은` `참고로` — presentation filler
- `~할 수 있을 것 같습니다` — stacked hedging. If it is unknown, say it is unknown, once
- `확인 필요.` `진행 예정.` — a noun standing in for a sentence. End on a verb
- `좋습니다` `훌륭합니다` `잘 진행되고 있습니다` — praise. The user can see the numbers
- `또한` `더불어` `나아가` in consecutive sentences

**Words to use.** Short declaratives, one fact each. Verbs over nouns. The user's own
vocabulary from the ledger, unparaphrased — renaming their item makes it unsearchable. Bad
news first, with no cushion in front of it.

**Numbers** come from the script output, copied. Never recomputed, never rounded by eye.

**Emoji** belong to the card, which uses a fixed set of seven as section markers. Do not
add your own, do not put one inside a line that has to line up with the line above it, and
do not decorate your prose with them — the card already carries the scanning aids.
