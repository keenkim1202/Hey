<div align="center">

```
        ─── hey ─────────────────────────  2026-08-05 (수)

         🕘 어제        CSV 임포트 파이프라인 머지 (#20)
         🔧 이어갈 자리  wt-checkout  커밋 1건 PR 없음
         📋 체크리스트   3 / 13 칸        ████░░░░░░░░░░░░░░
         🎯 오늘        AI 1.0 중 0.4    닫을 수 있는 하위 항목 2개
```

# hey

**마크다운 원장 한 장으로 일을 굴린다.** 체크리스트, 산정, 아침 브리핑, 마감 기록 —
사람이 직접 읽고 고치는 파일 하나에서 전부 나온다.

[![ci](https://img.shields.io/github/actions/workflow/status/keenkim1202/Hey/ci.yml?branch=main&style=flat-square&label=ci)](https://github.com/keenkim1202/Hey/actions/workflows/ci.yml)
[![license](https://img.shields.io/badge/license-MIT-blue?style=flat-square)](../../LICENSE)
[![stars](https://img.shields.io/github/stars/keenkim1202/Hey?style=flat-square&color=e3b341)](https://github.com/keenkim1202/Hey/stargazers)
[![Claude Code](https://img.shields.io/badge/Claude%20Code-plugin-d97757?style=flat-square)](https://code.claude.com/docs/en/plugins)
[![python](https://img.shields.io/badge/python-3.9%2B-3776ab?style=flat-square)](https://www.python.org/)
[![no server](https://img.shields.io/badge/data-stays%20local-2ea043?style=flat-square)](#-데이터-위치)

[English](../../README.md) · **한국어**

</div>

> 배포 기준 문서는 루트의 [README.md](../../README.md) 다. 이 파일은 한국어 사용자를 위한
> 번역이며, 내용이 갈리면 영문판을 따른다.

---

## ⚡ before / after

**before.** 수요일 아침이다. 화요일에 뭘 했더라. `git log` 를 훑고, 워크트리 세 개를 열어
커밋 안 된 게 어디 있는지 찾고, 스프린트가 얼마나 남았는지 어림하고, 그러다 제일 시끄러운
것부터 손댄다.

**after.** 명령 하나, 카드 한 장.

```
─── orchard ────────────────────────────────────────────────── 2026-08-05 (수)

🕘 어제  08-04 (화)
   · CSV 임포트 파이프라인 머지 (#20). CSV 603행을 카탈로그로 매핑
   · Currency 엔티티 머지 (#19)

🔧 이어갈 자리
   · wt-checkout  feat/csv-import  커밋 1건 PR 없음

📋 진행
   체크리스트  3 / 13 칸 닫음             (23.1%)  ████░░░░░░░░░░░░░░
   산정        0.4 / 5.6 AI-일 완료       남은 5.2 · 착수 1.0
   이번 주     0.6 / 5.0 AI-일            페이스 2.4 뒤짐 (월-금)

📈 산출  08-04 (화)
   작업량   0.00 AI-일          최고 1.64 — 07-29 (수)
   코드량   38,330줄            최고 38,330줄 — 08-04 (화)
   토큰량   1.9M                최고 4.2M — 07-30 (목)
    1  07-29 (수)  ████████████████████      1.64  최고
    2  07-30 (목)  █████████▊                0.80
    3  08-03 (월)  ███████▎                  0.60

🎯 오늘 후보
   1. OrchardClient 전송 계층 — 남은 것은 `AuthMiddleware` 와
      `RetryingMiddleware` 다. #19 로 토큰 쪽이 먼저 들어왔으므로 401 refresh
      가 붙을 자리가 준비됐다
   2. Domain/Data Account — 국가 목록·소셜 로그인 실연결. `Onboarding` 스텁
      2개가 여기서 걷힌다
   3. Navigation 모듈 — `Onboarding` 의 `TODO(routing)` 2건이 여기 걸려
      있다

🚧 막힌 것 3
   · 백엔드에 2xx 선언 추가 요청
   · prod 호스트 확정
   · X-Region 헤더 필수 여부
```

섹션 표시는 이모지 7개고, 카드가 쓰는 것은 그게 전부다. **이번 주** 는 주간 목표를 잡아야
나오고, **산출** 은 비교할 기록이 쌓여야 나온다. 갓 설치한 상태에서는 둘 다 안 보인다.

숫자는 스크립트가 낸다. 모델이 읽어가며 더한 값이 아니다. 그 아래에 붙는 판단 — 무엇을
이어갈지, 무엇을 건너뛸지, 실제로 막힌 게 무엇인지 — 이 스크립트가 못 하는 부분이다.
카드 자체는 그대로 출력된다. 스킬이 요약으로 대체하는 것은 금지돼 있다.

---

## 🧩 구조

세 조각이고, 그중 손댈 것은 하나뿐이다.

**원장** 은 프로젝트 안의 마크다운 파일 하나, `TASKS.local.md` 다. 체크박스, 산정치,
작업 로그, 메모. 다른 파일과 똑같이 읽고 고친다. 커밋하지 않는다.

```markdown
- [ ] **소셜 로그인 4종** — Apple / Google / GitHub / Microsoft — 6 MD / AI 3.4
  - [x] Apple 로그인
  - [ ] Google 로그인
```

**스크립트** 가 그 파일을 파싱해 계산을 전부 한다 — 박스 집계, 공수 합계, 일별 산출, 랭킹,
번다운, 산정 편차. `hey.py` 와 `board.py`, 파이썬 표준 라이브러리만 쓴다.

**스킬** 이 모델이 읽는 부분이다. 어떤 스크립트를 부르고 결과를 어떻게 읽을지 적혀 있고,
모델이 하면 안 되는 것에 대해 엄격하다. 숫자를 눈대중으로 쓰지 않는다, 없는 로그를 지어내지
않는다, 대신 커밋하지 않는다.

이 분리가 설계의 전부다. 스크립트가 정확하니 모델은 잘하는 일만 하면 된다.

---

## 📦 설치

터미널에서 한 줄.

```bash
claude plugin marketplace add keenkim1202/Hey && claude plugin install hey@hey
```

Claude Code 안에서라면.

```
/plugin marketplace add keenkim1202/Hey
/plugin install hey@hey
```

`hey@hey` 가 이상해 보이지만 맞다. `<플러그인>@<마켓플레이스>` 이고 둘 다 이름이 `hey` 다.
첫 명령이 카탈로그를 등록하고 두 번째가 거기서 설치한다. 설치에 카탈로그가 필요하므로 순서가
있다. 둘 다 다시 실행해도 안전하다.

프로젝트를 등록하고 원장을 만든다.

```
/hey-ledger      # 이 프로젝트를 등록하고 원장 생성
/hey-plan        # 스펙이나 할 일 목록을 붙여넣으면 산정치가 붙은 체크리스트가 나온다
/wassup          # 내일 아침, 여기서 시작
```

로컬 체크아웃으로 개발하며 쓸 때는 경로를 등록한다.

```bash
claude plugin marketplace add /path/to/hey && claude plugin install hey@hey
```

원장을 손으로 만들려면 `plugins/hey/templates/LEDGER.ko.md` 를 복사한다. 영문 원장은
`LEDGER.md` 다. **섹션 이름은 두 언어 모두 인식되므로 어느 쪽이든 동작한다.**

원장은 git 에 넣지 않는다 — `.git/info/exclude` 가 기본 자리다.

### Codex

Codex 도 같은 마켓플레이스 파일을 읽고, Codex 자체 플러그인 검증기를 통과한다.

```bash
codex plugin marketplace add keenkim1202/Hey && codex plugin add hey@hey
```

Codex 는 `skills/` 의 스킬 9개를 로드한다. `/hey` 는 스킬이 아니라 커맨드라서, 세션 시작 훅은
Codex 플러그인 매니페스트가 받는 컴포넌트가 아니라서 각각 로드되지 않는다. 스킬은
`$CLAUDE_PLUGIN_ROOT` 로 스크립트를 찾고, 없으면 Codex 가 쓰는 이름인 `$PLUGIN_ROOT` 로
넘어간다.

**설치는 검증했고, 실제 Codex 세션에서 스킬을 돌려본 것은 아니다.** 스킬이 스크립트를 못
찾는다고 하면 그 변수 문제이니 이슈로 남겨주면 좋다.

---

## 🎛 명령

| 명령 | 무엇 |
|---|---|
| `/hey-ledger` | 프로젝트 등록, 스코프 설정, 원장 생성. 나머지가 참조하는 규약 |
| `/wassup` | 하루 시작 — 어제 한 일, 오늘 분량, 이어갈 자리, 리더보드 |
| `/seeya` | 하루 마감 — 오늘 기록, 실적 집계, 내일 예고 |
| `/hey <내용>` | 즉시 메모. 날짜·브랜치·커밋이 자동으로 붙는다 |
| `/hey-plan` | 스펙을 체크리스트로 쪼개고 MD·AI 산정치를 붙인다 |
| `/hey-tune` | 산정치를 조율하고 바꾼 이유를 원장에 남긴다 |
| `/hey-sync` | 원장 갱신 — 체크, 집계, PR 기록, 다음 착수 순서 |
| `/hey-run` | 범위를 정해 루프로 처리하고 요약 보고. 병렬 가능 항목도 추천 |
| `/hey-recap` | 주간 회고 — 번다운, 이월, 산정 편차 |
| `/hey-standup` | 스탠드업 3줄. 지표도 퍼센트도 넣지 않는다 |

세션 시작 훅이 하나 있다. **커밋도 PR 도 없이 떠 있는 작업이 있을 때만** 말한다. 가장 잃기
쉬운 상태이기 때문이다. 그 외에는 아무 말도 하지 않는다.

---

## 📐 산정

항목마다 숫자를 둘 잡는다. 하나로는 따질 거리가 안 되기 때문이다.

| | 뜻 |
|---|---|
| `MD` | 도구 없이 재던 전통 man-day |
| `AI` | 도구를 쓸 때의 환산 man-day. `AI 1.0` 이 8시간 하루 |

`/hey-plan` 은 항목을 코드 작업과 사람-게이트 작업으로 쪼개 배수를 따로 건다. 둘이 같은
비율로 줄지 않기 때문이다.

| 종류 | 배수 |
|---|---|
| 스캐폴드, 매핑, 보일러플레이트 | 6-7x |
| 스펙이 확정된 UI | 5-6x |
| API 에 연결된 화면 | 3-4x |
| 상태 기계, 동시성 | 1.5-3x |
| **사람-게이트** — 외부 콘솔·계정·인증서, 스토어 심사 | **1x** |

마지막 줄이 핵심이다. 외부에서 기다리는 시간은 도구가 좋아진다고 줄지 않는다. 그걸 나머지에
섞어 잡은 산정치는 틀리는 방향으로 누적된다. 모든 합계는 그중 1x 가 차지하는 비중을 같이
보고한다.

---

## 📈 지표

`/seeya` 가 하루에 한 번 세 가지를 기록한다.

| 지표 | 출처 |
|---|---|
| 작업량 | 원장에서 그날 닫힌 체크박스를 항목 산정치로 환산한 AI-일 |
| 코드량 | git 이 기록한 추가·삭제 줄 수. 프로젝트의 모든 워크트리 |
| 토큰량 | Claude Code 트랜스크립트 사용량. 모든 워크트리, 캐시 읽기는 제외 |

리더보드는 **내 지난 기록과의 비교**다. 다른 사용자 데이터를 보내거나 받지 않는다.

```
오늘  코드량 38,330줄    최근 5일 중 1위

 1  08-04 (화)  ████████████████████  38,330줄  최고
 2  08-03 (월)  ██████▋               12,846줄
 3  07-31 (금)  ████▉                 9,356줄
    평균        ██████▌               12,553줄

기록 경신. 오늘 쓴 건 슬롭이 아니었던 모양이다.  (38,330줄)
```

첫 기록은 **기준선**이라 작업량 수치를 남기지 않는다. 비교할 이전 날이 없어서 그날 닫혀
있던 박스를 세면 기록 시작 전에 끝난 일까지 계상되고, 그 숫자가 이후 모든 날의 최고 기록
자리를 차지하게 된다. 코드량과 토큰량은 첫날부터 정확하다.

세 지표가 서로 어긋나면 그것도 정보다. 코드량·토큰량이 높은데 작업량이 0 이면 일은 했는데
닫힌 항목이 없다는 뜻이다. 항목이 너무 크게 잡혔거나, 박스를 안 치고 있거나 둘 중 하나다.
`/seeya` 는 보기 좋은 숫자를 골라 쓰는 대신 어느 쪽인지 묻는다.

---

## 💡 알아둘 것

- **작업량은 소급되지 않는다.** 원장은 현재 상태만 담고 있어서 기록을 시작한 뒤부터만 일별
  작업량이 남는다. 코드량·토큰량은 git 과 트랜스크립트에 이력이 있어 소급된다. 같은 이유로
  산정 편차는 닫히기 전에 미완료 상태로 관측된 항목만 측정한다
- **미푸시 커밋은 리모트의 기본 브랜치를 기준으로 센다.** 등록 시점에 판별해 `base` 로
  저장한다. 판별에 실패하면 0 으로 찍지 않고 확인하지 못했다고 알린다. 기준 브랜치가 틀리면
  비교가 조용히 실패해서, 기기 밖으로 나가지 않은 작업이 그대로 묻힌다
- **항목 이름이 키다.** 과거 스냅샷이 `<단계>|<항목 이름>` 으로 연결되므로, 이름을 바꾸면
  이월·편차 추적이 끊긴다
- **산정치는 최상위 항목 줄에만** `N MD / AI M` 형태로 적는다. 하위 항목에는 붙이지 않는다
- 박스는 `[ ]`, `[x]`, `[X]` 셋이다. 그 외는 박스가 아니고 어디에도 집계되지 않는다
- 여러 프로젝트를 병행할 수 있다. `scope current` 는 현재 위치 하나, `scope all` 은 전부
- 원장 섹션 이름과 블로커 키워드는 **전 언어 별칭으로 매칭**하므로 설정 없이 동작한다

---

## 🌏 언어

기본은 영어다. `~/.hey/config.json` 에 `"lang": "ko"` 를 넣거나 `HEY_LANG=ko` 를 설정하면
한국어로 바뀐다. 사용자가 읽는 문구만 바뀌고, 저장되는 데이터는 언어와 무관하게 유지된다.

새 언어 팩은 `plugins/hey/scripts/strings.py` 에 넣는다. 언어를 키로 쓰는 테이블
(`WEEKDAYS`, `METRIC_LABELS`, `UNITS`, `CARD`, `FLAIR`, `STREAK`, `STATE_LABELS`,
`BLOCKER_WORDS`, `BLOCKER_SECTIONS`) 에는 언어 키를 추가하고, 섹션을 키로 쓰는 `SECTIONS`
에는 각 행에 번역한 제목을 덧붙인다. 한국어처럼 단어 경계가 없는 언어라면 `_bounded` 도
같이 손본다. 성격 문구의 어조 규칙은 그 파일 맨 위에 적혀 있다.

---

## 🗂 데이터 위치

```
~/.hey/config.json          등록된 프로젝트와 각자의 기준 브랜치·목표, 기본 스코프, 언어
~/.hey/stats.jsonl          일별 스냅샷. 랭킹·번다운·이월·편차가 여기서 나온다
<프로젝트>/TASKS.local.md    원장
```

이게 전부고, 기기 밖으로 나가는 것은 없다. 프로젝트의 `base` 는 등록할 때 채워진다. 바꾸려면
`config.json` 을 고치거나 `--base <브랜치>` 로 등록을 다시 한다.

**목표는 프로젝트별이다.** 여러 프로젝트를 등록하면 각자 주간·일간 목표를 따로 가진다. 하나의
숫자를 나눠 쓰는 일부에 대고 재면 모든 프로젝트가 미달로 보이기 때문이다. 목표는 잡기 전까지
없는 상태이고, 카드의 **이번 주** 줄도 그때까지 나오지 않는다.

```bash
python3 plugins/hey/scripts/board.py goal --set 5.0
```

무언가 아무것도 안 나오는데 이유를 모르겠으면 점검을 돌린다. 기준 브랜치, 원장에 빠진 섹션,
산정치 없는 항목, 손상된 기록 파일을 한 번에 보고한다. 전부 원래는 에러가 아니라 빈 결과로
나타나는 것들이다.

```bash
python3 plugins/hey/scripts/hey.py doctor
```

---

## 🛠 개발

```
plugins/hey/
├── .claude-plugin/       Claude Code 용 매니페스트
├── .codex-plugin/        Codex 용 매니페스트
├── skills/
│   ├── hey-ledger/       원장 규약. 나머지 스킬이 이걸 읽는다
│   └── .../              스킬 하나당 디렉터리 하나
├── commands/hey.md       /hey, 메모 캡처 커맨드
├── scripts/
│   ├── hey.py            원장 파싱, 집계, 기록
│   ├── board.py          일별 산출, 리더보드, 카드 두 장
│   ├── strings.py        사용자가 읽는 모든 문구, 언어별
│   └── selftest.py       정적 검사 후 픽스처를 상대로 전 명령 실행
├── hooks/hooks.json      세션 시작 훅이 언제 뜨는지
├── hooks-handlers/       on-session-start.py, 실제로 도는 것
└── templates/            LEDGER.md, LEDGER.ko.md
```

매니페스트 둘이 다른 것은 의도다. Claude Code 쪽은 `version` 이 없어서 모든 커밋이 바로
사용자에게 닿고, Codex 는 엄격한 semver 를 요구해서 `.codex-plugin/plugin.json` 에 버전을
박아 두고 Codex 사용자가 업데이트를 보려면 올려줘야 한다.

자체 점검은 정적 검사로 시작한다 — 매니페스트가 파싱되는지, 스킬마다 이름과 설명이 있는지,
같은 이름을 쓰는 컴포넌트가 없는지. 그다음 git 리모트·연결된 워크트리·씨앗 원장을 갖춘
픽스처 프로젝트를 만들고 전 명령을 거기에 돌린다. 실제 프로젝트나 설정은 건드리지 않는다.
`HEY_HOME` 과 트랜스크립트 경로가 둘 다 임시 디렉터리를 가리킨다.

```bash
python3 plugins/hey/scripts/selftest.py
python3 plugins/hey/scripts/selftest.py --lang ko
```

CI 가 Linux 와 macOS 에서 둘 다 돌리고, README 가 말하는 하한을 지키려고 Linux 는 python 3.9
로 고정한다.

매니페스트를 Claude Code 자체 스키마로 검증하려면 CLI 가 필요해서 로컬 단계로 남겨 뒀다.

```bash
claude plugin validate .
claude plugin validate ./plugins/hey
```

**요구 사항:** python3 3.9 이상 (macOS 기본으로 충족) 과 git. `gh` 는 PR 기록에만 쓰이고,
없으면 그 단계만 건너뛴다.

`docs/social-preview.png` 는 `docs/social-preview.html` 에서 만든다. 레포 링크 미리보기를
이미지 편집기가 아니라 마크업으로 고치기 위해서다.

```bash
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
  --headless --disable-gpu --hide-scrollbars --force-device-scale-factor=2 \
  --window-size=1280,640 --screenshot=docs/social-preview.png \
  "file://$PWD/docs/social-preview.html"
```

2560x1280 로 떨어진다. GitHub 권장치 1280x640 의 두 배이고, 1x 로 렌더링하는 것보다 축소가
깔끔하다. Settings, General, Social preview 에 올린다.

---

## ❓ FAQ

### 🔒 기기 밖으로 나가는 게 있나?

없다. 서버도 텔레메트리도 없다. 리더보드는 `~/.hey/stats.jsonl` 에 쌓인 내 지난 기록과
오늘을 비교하는 것이다.

### 📁 원장을 커밋해야 하나?

아니고, 하지 않는 게 맞다. 사용자별 로컬 상태다. `.git/info/exclude` 가 보통 자리다.

### 🔢 산정 숫자가 왜 하나가 아니라 둘인가?

`MD` 는 남들이 이미 그 단위로 생각하는 숫자고, `AI` 는 내가 실제로 지키는 숫자이기 때문이다.
둘을 같이 두면 일정이 협상 가능해진다. 어느 배수에 동의하지 않는지 짚을 수 있다.

### 0️⃣ 하루 종일 일했는데 작업량이 왜 0 인가?

닫힌 체크박스가 없기 때문이다. 보통은 항목이 하루에 닫기엔 너무 크게 잡힌 경우다. 이 지표는
일부러 뭉개지 않는다. 0 은 0 으로 보고한다.

### ✋ 모델이 원장을 마음대로 고칠 수 있나?

스킬이 금지한다. 회고와 브리핑은 읽기 전용이고, `/hey-sync` 는 바뀐 줄만 고치고, 산정치는
이유 없이 다시 계산하지 않고, 대신 커밋하거나 푸시하지 않는다.

### 🗂 모노레포나 여러 프로젝트를 동시에 써도 되나?

된다. 각각 등록하고 `scope all` 로 두면 아침에 한 번에 훑는다.

### 👀 카드가 왜 안 보이나?

보여야 한다. `/wassup` 과 `/seeya` 는 자기 말을 하기 전에 카드를 원문 그대로 붙인다. 도구
출력은 모델에게만 보이고 사용자에게는 가지 않아서, 요약만 한 카드는 사용자가 못 본 카드다.
블록 없이 산문만 온다면 버그이니 이슈로 남겨주면 좋다.

---

## 📄 라이선스

MIT. [LICENSE](../../LICENSE) 참고.
