# codex-image-in-cc 사용 가이드 (한국어)

> Claude Code에서 OpenAI Codex CLI의 `imagegen` 스킬을 슬래시 명령으로 호출해 **이미지를 생성·편집·스타일 매칭·배치 오케스트레이션**하는 플러그인.

원본 [KingGyuSuh/codex-image-in-cc](https://github.com/KingGyuSuh/codex-image-in-cc)의 fork이며, 이 fork(gmlxo76)에서 **`/codex-image:style-gen`**과 **`/codex-image:asset-pipeline`** 두 명령을 추가했습니다.

영문 README는 [README.md](README.md), 아키텍처 상세는 [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md), 변경 이력은 [CHANGELOG.md](CHANGELOG.md) 참조.

---

## 한 줄 요약 설치

```bash
claude plugin marketplace add gmlxo76/codex-image-in-cc
claude plugin install codex-image@codex-image-in-cc
```

이 두 줄이면 끝. 그 다음 Claude Code 세션에서 `/codex-image:status` 입력해서 `Ready: yes` 나오는지 확인.

---

## 무엇을 하는 플러그인인가

| 기능 | 명령어 | 한 줄 |
|---|---|---|
| 환경 점검 | `/codex-image:status` | Node/Codex/로그인/imagegen 스킬 체크 |
| 텍스트로 새 이미지 | `/codex-image:generate` | 프롬프트만으로 N장 생성 |
| 기존 이미지 편집 | `/codex-image:edit` | 입력 이미지를 받아 수정 (배경 교체 등) |
| 스타일 매칭 새 이미지 ⭐ | `/codex-image:style-gen` | 레퍼런스의 비주얼 스타일로 다른 주제 새로 생성 |
| 배치 리소스화 ⭐ | `/codex-image:asset-pipeline` | 레퍼런스 + 프로젝트 컨텍스트로 자산 목록 계획 → 일괄 생성 |

⭐는 이 fork에서 추가된 기능.

---

## 사전 요구사항

| 항목 | 최소 / 조건 |
|---|---|
| Node.js | 18.18 이상 |
| `@openai/codex` CLI | 0.124 이상 |
| Codex 로그인 | `codex login` 완료 (ChatGPT 로그인 또는 API 키 둘 다 가능) |
| `OPENAI_API_KEY` | **불필요** (내장 `image_gen` 도구 사용) |
| Claude Code | 플러그인 지원 버전 |

설치/업데이트:

```bash
npm install -g @openai/codex@latest
codex login
```

---

## 설치 (자세히)

### 마켓플레이스에서 (권장)

```bash
claude plugin marketplace add gmlxo76/codex-image-in-cc
claude plugin install codex-image@codex-image-in-cc
```

설치 후 새 슬래시 명령을 잡으려면:

```
/reload-plugins
```

또는 Claude Code 재시작.

스코프는 기본 `user`. 프로젝트 단위 설치는 `--scope project`, 세션 단위는 `--scope local` 추가.

### 로컬 클론에서 (개발/수정 목적)

```bash
git clone https://github.com/gmlxo76/codex-image-in-cc.git
cd codex-image-in-cc
claude plugin marketplace add "$PWD"
claude plugin install codex-image@codex-image-in-cc
```

이렇게 하면 로컬 파일을 직접 수정하면서 `/reload-plugins`로 반영 가능.

---

## 슬래시 명령어 상세

### `/codex-image:status`

설치 상태/로그인/필수 의존성 점검. 처음 셋업했거나 에러 날 때 먼저 실행.

```bash
/codex-image:status
```

출력 예:

```
Codex Image status
Ready: yes
OK Node: v24.x (minimum 18.18.0)
OK Codex: codex-cli 0.130.0 (minimum 0.124.0)
OK Codex login: Logged in using ChatGPT
OK Headless exec: `codex exec --full-auto` accepted
OK imagegen skill: C:\Users\<...>\.codex\skills\.system\imagegen\SKILL.md
```

---

### `/codex-image:generate "프롬프트"`

순수 텍스트 프롬프트로 새 이미지 생성. 출력 경로/사이즈/장수/투명도/품질 모두 **자연어**로 표현.

```bash
/codex-image:generate "A watercolor moonlit library, save to images/library.png at 1024x1024"
/codex-image:generate "5 logo variations of a brass compass on white, save under images/logos/"
/codex-image:generate "A standalone tarot card icon with transparent background, save to icons/tarot.png at 512x512"
```

플래그 없음. 모든 옵션은 프롬프트 자연어 안에.

---

### `/codex-image:edit <입력경로> "편집 지시"`

기존 이미지를 입력으로 받아 편집. 첫 토큰은 입력 이미지 경로 (공백 포함 시 따옴표).

```bash
/codex-image:edit input.png "Replace the background with a clean white studio backdrop, save to edited.png"
/codex-image:edit "my photo.png" "tint blue, save to my_photo_blue.png"
```

**Claude Code UI 첨부 이미지**도 지원 — 채팅에서 이미지 드래그해서 `[Image #1]` 표시된 상태로 명령 입력하면 플러그인이 첨부의 실제 경로를 자동 감지.

---

### `/codex-image:style-gen <레퍼런스경로> "프롬프트"` ⭐

레퍼런스 이미지의 **시각 스타일**(팔레트/선/명암/구도/무드)을 따라서 **새로운 주제**의 이미지 생성. 레퍼런스는 절대 수정되지 않고 저장도 안 됨 (스타일만 빌려옴).

```bash
/codex-image:style-gen reference.png "A coin in this exact style, transparent background, save to assets/coin.png at 512x512"
/codex-image:style-gen "concepts/hero.png" "5 variations of small UI buttons in the same style, save under assets/ui/"
```

#### `edit` vs `style-gen` 결정 표

| | `edit` | `style-gen` |
|---|---|---|
| 첨부 이미지 역할 | 편집 대상 | 스타일 참조만 |
| 저장되는 것 | 입력의 수정된 버전 | 완전히 새로 그려진 이미지 |
| 입력 레이아웃 보존 | ✓ (사용자가 요청하지 않는 한) | ✗ — 비주얼 스타일만 빌려옴 |
| 레퍼런스 자체 수정/출력 | (편집된 버전이 출력) | 절대 없음 |

#### 동작 원리

내부적으로 `codex exec --image <reference> -- "<특수 prefix> + <사용자 프롬프트>"`로 호출.  
특수 prefix가 **"attached image is a STYLE REFERENCE ONLY, treat as generate not edit"**라고 명시하기 때문에 Codex의 `imagegen` 스킬이 [공식 role classification](https://github.com/openai/codex/blob/main/codex-rs/skills/src/assets/samples/imagegen/SKILL.md)에 따라 "supporting style input"으로 해석하고 `generate` 경로를 탐.

---

### `/codex-image:asset-pipeline <레퍼런스경로> "프로젝트 컨텍스트"` ⭐⭐

레퍼런스 + 프로젝트 컨텍스트(게임/앱/웹) → 자산 목록 자동 계획 → 사용자 검토 → 일괄 `style-gen` 호출. **배치 작업용**.

```bash
/codex-image:asset-pipeline reference.png "RPG mobile game: 5 enemies + 10 items + 4 backgrounds + UI buttons"
/codex-image:asset-pipeline concepts/hero.png "SaaS landing: hero, 4 section illustrations, OG image, favicon"
/codex-image:asset-pipeline mockup.png "casual puzzle app: app icon, splash, 6 tile sprites, particle textures"
```

#### 흐름

```
1. parse-args 호출 (인자 검증)
2. Claude Code 에이전트가 컨텍스트 + 레퍼런스 보고 자산 목록 제안
   (Codex turn 사용 안 함 — 텍스트 추론만, 토큰 절약)
3. 사용자에게 plan을 표로 보여주고 AskUserQuestion으로 확인
   - 승인 / 수정 / 취소
4. 승인되면 ./codex-images/manifest-<UTC>.json 저장
5. 항목 10개 초과 시 sample-first 게이트:
   - 먼저 3장만 생성 → 사용자에게 보여주고 진행 여부 확인
6. 나머지 순차로 style-gen 호출 (병렬 불가)
7. 최종 리포트 (성공/실패/매니페스트 경로/토큰 합계)
```

#### Claude Code UI에서 이미지 첨부로 호출 (가장 편함)

채팅 입력창에 이미지 드래그 → `/codex-image:asset-pipeline` 입력 후 컨텍스트만 적기:

```
/codex-image:asset-pipeline 이 컨셉을 게임 리소스로 만들어줘, 캐릭터 5명 + UI 아이콘 + 배경
```

플러그인이 `[Image #1]` placeholder를 자동으로 실제 경로로 치환합니다.

#### 비용

자산 1개당 약 20-35k Codex 에이전트 토큰 + `image_gen` 도구 1회. 30장 배치면 ~900k 토큰.  
**sample-first**는 정확히 이 비용을 잘못된 스타일에 낭비하지 않으려고 설계된 게이트.

---

## 전형적 워크플로우 (컨셉 → 리소스화)

```
1️⃣ 컨셉 탐색
   /codex-image:generate "moody fantasy RPG concept art with hero, dark forest, 1024x1024"
   /codex-image:generate "4 variations of a fantasy RPG hero card design, mystical"
   → 변주 여러 장 뽑고 마음에 드는 것 선택

2️⃣ 스타일 락
   선택한 컨셉을 references/style.png 같은 경로로 보관

3️⃣ 리소스화
   /codex-image:asset-pipeline references/style.png "modern fantasy RPG mobile: 5 enemies + 8 items + UI buttons + app icon"
   → Claude Code가 자동으로 자산 목록 제안 → 검토 → 승인 → 일괄 생성
```

---

## 자연어 옵션 (모든 명령 공통)

플러그인은 프롬프트를 가공하지 않고 거의 그대로 Codex에 넘김. 명령형으로, 한국어/영어 둘 다 가능. 다만 다음 항목들은 빠뜨리지 않는 게 좋음:

| 항목 | 자연어 예시 |
|---|---|
| 저장 경로 | `save to D:\path\to\file.png` 또는 `save under D:\path\to\folder\` |
| 사이즈 | `at 1024x1024`, `512x512 square`, `portrait 768x1024` |
| 장수 | `5 variations`, `single image`, `3 different angles` |
| 품질 | `high quality`, `low quality draft` |
| 투명 배경 | `transparent background`, `with alpha channel` |
| 스타일 | `watercolor`, `pixel art`, `photorealistic` (style-gen에선 불필요 — 레퍼런스가 스타일 제공) |

---

## 알려진 제약

### 1. 해상도가 정확히 일치 안 할 수 있음
내장 `image_gen` 도구가 요청 사이즈보다 크게 반환할 때가 있고, codex가 `sips`/Pillow로 후처리해서 맞춰주긴 하지만 정확한 픽셀이 보장되지는 않음.

### 2. "원본 이미지에서 특정 요소만 분리"는 약함
`/codex-image:edit`로 "이 mockup에서 캐릭터만 빼달라" 같은 요청을 주면 사각형 영역 크롭 정도만 됨. **차선책**: `/codex-image:style-gen`로 "같은 스타일의 그 캐릭터를 transparent bg로 새로 그리기"가 훨씬 잘 됨. (단 픽셀 일치는 아님 — 같은 스타일의 새 캐릭터)

### 3. 토큰/비용
이미지 1장당 ~20-35k Codex 에이전트 토큰 + image_gen 도구 사용. asset-pipeline 30장 배치면 ~900k 토큰.

### 4. Codex 동시 호출 불가
`asset-pipeline`은 **순차 실행 강제**. 병렬로 여러 style-gen을 동시에 호출하면 codex CLI 세션이 충돌함.

### 5. Windows + Node 22+ spawning 이슈
플러그인이 자동 우회 (`%APPDATA%\npm\node_modules\@openai\codex\bin\codex.js` 직접 실행). 사용자가 신경 안 써도 됨.

### 6. Git 저장소가 아니어도 동작
`--skip-git-repo-check`가 자동으로 들어가서 에셋 폴더/스크래치 폴더에서도 잘 동작.

---

## 트러블슈팅

| 증상 | 해결 |
|---|---|
| `Codex unavailable` / `not found` | `npm install -g @openai/codex@latest` |
| `Codex login: not logged in` | `codex login` 재실행 |
| `imagegen skill: not found` | codex CLI 버전 0.124 미만. 위 명령으로 업데이트 |
| 슬래시 명령이 안 잡힘 | `/reload-plugins` 또는 Claude Code 재시작 |
| `Input/Reference image not found` | 절대경로인지, 파일이 실제로 있는지 확인 |
| style-gen이 레퍼런스를 편집한 듯한 결과 | 시스템 prefix에 "DO NOT modify reference"가 들어가 있음에도 발생하면 GitHub 이슈로 보고해주세요 |
| asset-pipeline이 30장 넘게 제안 | SKILL.md 정책은 5-10 starter set. 사용자가 "Refine"으로 줄이거나 컨텍스트를 더 구체적으로 |
| 결과가 엉터리 (요청한 분리/편집이 안 됨) | 프롬프트를 더 구체적으로. "캐릭터만 추출"보다 "캐릭터를 transparent bg로 새로 그리기" |

---

## 명령어 호출이 안 될 때 디버깅 순서

1. `/codex-image:status` 실행 → 모든 OK?
2. 캐시 디렉토리 확인 — `C:\Users\<당신>\.claude\plugins\cache\codex-image-in-cc\codex-image\<version>\skills\` 에 `asset-pipeline` `edit` `generate` `status` `style-gen` 5개 폴더 있나?
3. `claude plugin list | grep codex-image` 가 v0.3.0+ 표시?
4. 새 명령 추가 후라면 `/reload-plugins` 실행했는지 확인
5. Codex CLI 단독 확인 — `codex exec --full-auto --help` 가 정상 응답하나?

---

## 원작자 / 라이선스

이 fork는 [KingGyuSuh/codex-image-in-cc](https://github.com/KingGyuSuh/codex-image-in-cc) (Apache-2.0)의 derivative work입니다. 원작자의 `generate`/`edit`/`status` 명령과 디스패처 아키텍처는 변경 없이 유지되며, gmlxo76이 `style-gen` + `asset-pipeline` 명령을 추가했습니다.

자세한 변경 사항: [NOTICE](NOTICE), [CHANGELOG.md](CHANGELOG.md).

라이선스: [Apache-2.0](LICENSE).
