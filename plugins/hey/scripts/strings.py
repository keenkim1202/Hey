#!/usr/bin/env python3
"""User-facing text for hey, in every supported language.

English is the default. Set `"lang": "ko"` in ~/.hey/config.json, or `HEY_LANG=ko`,
to switch. Only text the user reads lives here — mechanical errors stay in English
so bug reports are searchable.

Tone rules for the FLAIR pools, in any language:
  - No trending slang. Memes last months; these lines print every day.
  - Get the laugh from structure, not vocabulary: self-deprecation, reversal, brevity.
  - Do not celebrate achievement. Overpraise reads as a yes-man and stops landing
    the second time it appears.
"""

from __future__ import annotations

import os
import re

WEEKDAYS = {
    "en": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
    "ko": ["월", "화", "수", "목", "금", "토", "일"],
}

# Section markers. Not per-language, and not decoration: they exist so a reader can find
# the section they want without reading the labels. One per section header, never inside a
# column that has to line up, and the same glyph for the same meaning every single day.
# A set this small stays a scanning aid; a bigger one turns the card into noise.
#
# Only single-codepoint emoji whose East Asian Width is `W`. Anything carrying a variation
# selector (U+FE0F, as in the warning sign) measures narrow but draws wide in most
# terminals, which silently breaks every aligned row below it. The self-test enforces this.
MARK = {
    "progress": "📋",
    "log": "🕘",
    "resume": "🔧",
    "notes": "📝",
    "results": "📈",
    "next": "🎯",
    "blocked": "🚧",
}

METRIC_LABELS = {
    "en": {"ai": "closed", "code": "code", "tokens": "tokens"},
    "ko": {"ai": "작업량", "code": "코드량", "tokens": "토큰량"},
}

UNITS = {
    # Every metric carries its own unit, so a bare number never reaches a card. The
    # leaderboard prints values on rows of their own, with no label to inherit from.
    "en": {"lines": " lines", "aid": " AI-days", "tok": " tokens"},
    "ko": {"lines": "줄", "aid": " AI-일", "tok": " 토큰"},
}

CARD = {
    "en": {
        "yesterday": "Yesterday", "today_did": "Done today",
        "resume": "Pick up here", "loose": "Not wrapped up",
        "notes": "Notes",
        "progress_head": "Progress",
        "checklist": "Checklist", "boxes_closed": "{done} / {total} boxes closed",
        "effort": "Effort", "effort_val": "{done} / {total} AI-days closed",
        "effort_note": "{left} left · {wip} in progress",
        "results": "Output",
        "today_next": "Today", "tomorrow_next": "Tomorrow",
        "blocked": "Blocked", "no_record": "no record — no log, no commits",
        "and_more": "and {n} more — `hey.py blockers` lists them",
        "waiting_days": "{n}d waiting",
        "commits_unpushed": "{n} commit(s) unpushed",
        "commits_unpushed_all": "{n} commit(s), branch never pushed",
        "uncommitted": "{n} uncommitted",
    },
    "ko": {
        "yesterday": "어제", "today_did": "오늘 한 일",
        "resume": "이어갈 자리", "loose": "정리 안 된 작업",
        "notes": "메모",
        "progress_head": "진행",
        "checklist": "체크리스트", "boxes_closed": "{done} / {total} 칸 닫음",
        "effort": "산정", "effort_val": "{done} / {total} AI-일 완료",
        "effort_note": "남은 {left} · 착수 {wip}",
        "results": "산출",
        "today_next": "오늘 후보", "tomorrow_next": "내일 후보",
        "blocked": "막힌 것", "no_record": "기록 없음. 작업 로그도 커밋도 없다",
        "and_more": "외 {n}건 — `hey.py blockers` 로 전체를 봅니다",
        "waiting_days": "{n}일째",
        "commits_unpushed": "커밋 {n}건 미푸시",
        "commits_unpushed_all": "커밋 {n}건, 브랜치 미푸시",
        "uncommitted": "미커밋 {n}개",
    },
}

FLAIR = {
    "en": {
        "zero": [
            "Zero. The day left a trace, the checkboxes did not. One of them is lying.",
            "Zero. Work happened; the ledger disagrees. Check for a subitem you can close.",
            "Zero. Size items too big and a month of work still prints this.",
        ],
    },
    "ko": {
        "zero": [
            "0. 흔적은 남았는데 체크박스는 꿈쩍도 안 했다. 둘 중 하나가 거짓말하는 중이다.",
            "0 이다. 열심히는 했는데 체크박스가 안 믿어준다. 닫을 하위 항목 있는지 본다.",
            "0. 항목을 크게 잡으면 한 달을 갈아도 이 숫자가 나온다.",
        ],
    },
}



# Ledger headings differ per language. Every lookup matches the union of aliases so
# a Korean ledger and an English ledger both work with no configuration.
SECTIONS = {
    "notes": ("Notes", "메모"),
    "log": ("Work log", "작업 로그"),
    "next": ("Next up", "다음 착수 순서"),
    "summary": ("Summary", "진행 요약"),
}

# Item states. Internal identifiers, also written into stats.jsonl - English only.
DONE, WIP, TODO = "done", "wip", "todo"
STATE_LABELS = {
    "en": {DONE: "done", WIP: "in progress", TODO: "not started"},
    "ko": {DONE: "완료", WIP: "착수", TODO: "미착수"},
}


def section_aliases(key: str) -> tuple:
    return SECTIONS[key]


BLOCKER_WORDS = {
    "en": ("waiting", "blocked", "blocker", "tbd", "needs decision",
           "unconfirmed", "to confirm", "pending"),
    "ko": ("대기", "확인 필요", "블로커", "미정"),
}

BLOCKER_SECTIONS = {
    "en": ("Blocker",),
    "ko": ("블로커",),
}

HANGUL = re.compile(r"[가-힣]")

# Hangul offers no word boundary to anchor on, and particles and endings attach straight
# onto the stem, so a marker may legitimately continue: `대기중`, `대기하는`, `미정이다`.
# Only these continuations count as the same word. Any other Hangul syllable means a
# different word entirely — `대기업`, `대기실`, `미정리`.
KO_TAILS = "중이인은는을를과와만도의에서로랑까하한함해했임였"


def _bounded(word: str) -> str:
    """A pattern that matches `word` as a word, not as a fragment of a longer one.

    Plain substring matching produced silent false positives: `pending` fired inside
    `depending`, `대기` inside `대기업`. A falsely blocked item drops out of the loop
    candidates and starts accruing stuck-days, so this errs toward not matching.
    """
    if HANGUL.search(word):
        return re.escape(word) + rf"(?:(?=[{KO_TAILS}])|(?![가-힣]))"
    return r"\b" + re.escape(word) + r"\b"


_BLOCKER_RE = re.compile(
    "|".join(_bounded(w) for pack in BLOCKER_WORDS.values() for w in pack),
    re.IGNORECASE,
)


def blocker_hit(text: str) -> bool:
    """Does this item text mark itself as blocked, in any supported language?"""
    return bool(_BLOCKER_RE.search(text))


def blocker_sections() -> tuple:
    return tuple(w for pack in BLOCKER_SECTIONS.values() for w in pack)


def lang(cfg: dict | None = None) -> str:
    picked = os.environ.get("HEY_LANG") or (cfg or {}).get("lang") or "en"
    return picked if picked in WEEKDAYS else "en"


def card(key: str, lc: str, **kw) -> str:
    return CARD[lc][key].format(**kw)


def flair(kind: str, on: str, lc: str, **kw) -> str:
    """Pick by date so it rotates daily but stays stable within a day."""
    pool = FLAIR[lc][kind]
    seed = sum(int(c) for c in on if c.isdigit())
    return pool[seed % len(pool)].format(**kw)

