# 또박또박 · 한국어 받아쓰기 (korean-dictation-grader)

초등학생이 종이에 받아쓰기를 하고, 부모가 직접 확인하는 모바일 웹앱입니다.
현재 **1단계**입니다. 사진 업로드·OCR·AI 자동 채점은 제공하지 않으며, 가짜 결과나 정확도를 표시하지 않습니다.

## 설치와 실행

Python **3.10 이상**이 필요합니다. 앱 실행에는 추가 패키지·API 키·음성 서버가 필요 없습니다.

소스를 내려받아 압축을 풀거나 작업 폴더를 연 뒤 터미널에서 실행합니다.

```bash
cd korean-dictation-grader
python3 server.py
```

Windows에서는 `python server.py`로 실행할 수 있습니다. 브라우저에서 **http://127.0.0.1:8770/** 을 엽니다. 종료는 `Ctrl+C`입니다.
소스 폴더명이 `Test_wrt`라면 `cd Test_wrt`를 사용하세요.

### 같은 Wi-Fi의 태블릿·휴대전화에서 열기

```bash
python3 server.py --host 0.0.0.0 --port 8770
```

컴퓨터와 태블릿을 같은 Wi-Fi에 연결하고, 실행 창의 ‘태블릿 접속’ 주소를 태블릿 Chrome/Safari에서 엽니다.
컴퓨터는 켜져 있어야 합니다. 연결이 안 되면 컴퓨터 방화벽에서 **개인 네트워크**의 8770 포트를 허용하고 공유기의 기기 간 연결 차단 여부를 확인하세요.
기본 실행은 이 컴퓨터에서만 접속됩니다. 이 개발 서버의 공개 인터넷 배포는 이번 단계의 범위에 포함되지 않습니다.

### 사용 순서

1. 실명 대신 학생 **별명**을 등록하고 학생을 선택합니다.
2. 기본 한국어 문장 10개 중 연습할 문장을 선택합니다. 각 문장은 최대 200자로 수정하고 ‘문장 수정 저장’을 누릅니다. 문제 목록은 가족이 함께 쓰고 학습 기록은 학생별로 구분됩니다.
3. 종이와 연필을 준비하고 ‘연습 시작’을 누릅니다. 정답 문장은 읽는 동안 가려집니다.
4. 기본 두 번 읽습니다. 시작 전에 속도, 반복 1~3회, 문장 사이 쓰는 시간 5/10/20초를 선택할 수 있습니다. 재생 중에는 일시정지·계속 읽기·읽기 종료를 사용할 수 있습니다.
5. 듣기 후 부모가 종이를 보고 각 문장을 ‘잘했어요 / 다시 연습 / 미확인’으로 표시하고 저장합니다. 중간에 종료한 연습도 미확인 상태로 저장할 수 있습니다. 마지막 문장은 다 쓴 뒤 확인하세요.
6. ‘학습 기록’에서 지난 문장과 부모 확인 결과를, ‘오답노트’에서 다시 연습할 문장을 봅니다. 오답노트의 ‘이 문장 다시 연습’으로 해당 문장만 읽을 수 있습니다.

오답노트는 과거에 ‘다시 연습’으로 표시한 기록을 모읍니다. 이후 맞게 써도 과거 오류 기록은 보존되며, 숙달 처리·과거 확인 결과 수정·학생 삭제는 후속 단계입니다.

### 한국어 음성 안내

모바일 브라우저의 Web Speech API(`speechSynthesis`, `ko-KR`)를 사용합니다. 한국어 음성이 있는 최신 Chrome/Safari가 필요합니다.
기기 설정의 텍스트 읽어주기/음성 합성 메뉴에서 한국어 음성을 설치하세요. 한국어 음성이 없으면 안내를 표시하고 재생을 시작하지 않습니다.
음성 목록은 늦게 준비될 수 있으므로 잠시 기다린 뒤 시작하세요. 음성 서비스에 따라 네트워크가 필요하거나 문장이 기기의 음성 제공업체로 전달될 수 있습니다. 민감한 내용은 문장에 넣지 마세요.
실제 음색·음량·장시간 재생·모바일 일시정지 동작은 OS/브라우저에 따라 달라집니다. 화면을 켜 두고 사용하세요.

## 저장과 개인정보

- 학생 별명, 수정 문장, 학습 기록, 부모 확인 결과는 실행 컴퓨터의 `data/dictation.sqlite3`에 저장합니다. 날짜는 UTC로 저장하고 화면에서는 기기 시간대로 표시합니다.
- 연습 당시 문장 사본을 보존하여 문제 수정이 과거 기록을 바꾸지 않습니다.
- 학생 선택은 학습 기록을 구분하는 기능이며 학생별 로그인이나 접근 권한 분리는 아닙니다. 신뢰하는 가족 기기에서 사용하세요.
- `data/`, `cache/`, 음성 녹음, `.env`, SQLite 파일은 Git에서 제외됩니다. 아이 사진·실명·학교·연락처·비밀키를 코드나 커밋에 넣지 마세요. 이번 단계는 사진을 받지 않습니다.
- 백업은 서버를 종료하고 `data/` 폴더를 안전한 개인 저장소에 복사합니다. 초기화는 서버 종료 후 해당 데이터 파일을 삭제합니다. 삭제 전에 백업하세요.
- 별도 저장 위치: 환경변수 `DICTATION_DATA_DIR=/개인/폴더`를 지정하면 그 아래 `data/`를 사용합니다. 브라우저 테스트는 임시 폴더를 사용합니다.
- 가족 접근 암호가 필요하면 `config.json`의 `access.enabled`를 `true`로 바꾸고 재시작하세요. `python3 server.py --show-access`에서 암호를 확인합니다. 이 암호는 공유하지 마세요.

## 원본과 재사용 범위

원본: [zackzou/kids-memory-buddy](https://github.com/zackzou/kids-memory-buddy).
기준 커밋은 [docs/UPSTREAM_COMMIT](docs/UPSTREAM_COMMIT), 원본 설명은 [docs/UPSTREAM_README.md](docs/UPSTREAM_README.md)에 보존했습니다.
사용자가 제시한 `sujong00-spec/Test_wrt`는 화면상 빈 비공개 저장소였으므로 공개 원본을 가져와 개발했습니다. GitHub 업로드는 수행하지 않았습니다.

- 원본은 Python 표준 라이브러리 HTTP 서버(`server.py`, `core/webapp.py`), JSON 설정, SQLite 학습 기록, 중국어/영어 화면, OCR/TTS 공급자 모듈로 구성되었습니다.
- HTTP 서버·정적 파일 제공·기능 등록·접근 암호 기능을 재사용합니다. 한국어 화면은 `features/dictation/`, 한국어 학습 저장소/API는 `core/dictation.py`에 구현했습니다.
- 기존 기록에는 학생 구분이 없어 별도 SQLite 스키마를 사용합니다. 기존 `data/moxie.db` 등 원본 데이터는 자동 변환하거나 삭제하지 않습니다.
- 원본 `features/moxie/`, OCR/자동 채점/음성 공급자 코드는 후속 검토를 위해 남겨 두었지만 제품 서버에는 등록하지 않습니다. `/api/recognize`, `/api/result`, `/api/result/vision`, `/api/plan`은 404입니다. 원본 중국어 화면도 제품 경로로 제공하지 않습니다.
- MIT 라이선스와 **Copyright (c) 2026 zackzou** 고지를 [LICENSE](LICENSE)에 그대로 유지합니다.

## 테스트

앱 서버와 Python 테스트는 표준 라이브러리만 사용합니다.

```bash
python3 -m unittest discover -s test -p test_dictation.py -v
python3 test/test_text.py
python3 test/test_access.py
python3 test/test_local.py
python3 test/test_records.py --local
node test/test_player.mjs
python3 -m compileall -q server.py core features test
```

`test_player.mjs`는 Node.js 18 이상이 필요합니다. 음성 대역으로 한국어 선택·속도·두 번 읽기·대기 중 일시정지/재개·종료·오류를 검증합니다.
`test_local.py`는 원본 OCR/TTS 모듈의 로컬 대역 회귀 테스트이며 실제 OCR 결과나 제품 기능이 아닙니다. 시스템 음성이 없으면 해당 합성 검사는 건너뜁니다.
`test_records.py --local`은 `test/legacy_runtime.py`의 원본 테스트 전용 구성으로 동작합니다. 원본 데이터 저장소에 테스트 기록을 만들 수 있습니다.
원본 `test_api.py`와 `test_records.py`의 외부 OCR 모드는 1단계 대상이 아니며 외부 서비스 설정이 필요합니다.

선택적으로 브라우저 테스트 도구를 설치합니다(앱 실행에는 불필요).

```bash
python3 -m pip install playwright
python3 -m playwright install chromium
python3 test/browser_smoke.py
```

브라우저 테스트는 기본 `/usr/bin/chromium`을 사용하며 없으면 Playwright 설치 브라우저를 사용합니다. 실제 `server.py`를 8877 포트에서 시작·종료하고 임시 데이터로 검증합니다.
자세한 검증 결과와 실제 태블릿에서 남은 확인 사항은 [docs/VALIDATION.md](docs/VALIDATION.md)를 참고하세요.
