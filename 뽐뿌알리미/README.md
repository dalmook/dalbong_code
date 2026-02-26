# 뽐뿌 키워드 알림 + 텔레그램 관리 봇

Synology NAS(Docker)에서 동작하는 `뽐뿌 RSS 기반 키워드 알림 + 텔레그램 관리` 봇입니다.
키워드 등록/삭제/게시판 선택/알림 확인을 모두 텔레그램에서 처리합니다.

## 주요 기능
- 텔레그램에서 키워드 추가/삭제/목록/게시판 선택
- 사용자(chat_id) 단위 키워드 분리 저장 (SQLite)
- RSS 주기 폴링 + 키워드 매칭 + 중복 알림 방지(`sent`)
- 상태 머신 기반 입력 대기 (`ADD_WAIT`, `REMOVE_WAIT`)
- 가격 히스토리 적재/분석(알림용) 지원 (`deals`, `pricing.py`, `backfill_6m.py`)

## 파일 구성
- `app.py`: 텔레그램 봇 + RSS 폴링
- `db.py`: SQLite 저장소/스키마/헬퍼
- `pricing.py`: 제목 기반 가격 파싱/분석
- `backfill_6m.py`: 과거 6개월 백필(HTML 목록 크롤링)
- `tests/`: 단위 테스트

## 환경변수
- `BOT_TOKEN`: 텔레그램 봇 토큰 (필수, 실제 운영 시)
- `POLL_INTERVAL_SEC`: RSS 폴링 주기(초), 기본 `300`
- `DATA_DIR`: 데이터 디렉터리, 기본 `/data`
- `DB_PATH`: SQLite 파일 경로, 기본 `/data/ppompu_bot.sqlite3`
- `DEFAULT_BOARD_KEY`: 기본 게시판 키, 기본 `ppomppu`
- `BOARD_OPTIONS`: `key|label|url,key2|label2|url2`
- `LOG_FILE`: 로그 파일 경로(선택), 예: `/data/app.log`
- `DRY_RUN`: `1`이면 텔레그램 전송 대신 콘솔 출력
- `DRY_RUN_ONCE`: `1`이면 dry-run 1회만 실행

백필 관련:
- `BACKFILL_BOARD_ID` (기본 `ppomppu`)
- `BACKFILL_MONTHS` (기본 `6`)
- `BACKFILL_MAX_PAGES`

## Docker 실행
```bash
docker compose up -d --build
```

## .env 예시
```env
BOT_TOKEN=123456789:ABC...
POLL_INTERVAL_SEC=300
DEFAULT_BOARD_KEY=ppomppu
DRY_RUN=0
```

## Synology NAS 운영 메모
1. 프로젝트 경로 예시: `/volume1/docker/ppompu-bot`
2. 데이터 볼륨: `/volume1/docker/ppompu-bot/data` -> 컨테이너 `/data`
3. 텔레그램/뽐뿌 외부 접속이 가능한 네트워크 필요

## 텔레그램 UX
- 첫 진입: 텔레그램 `Start` 버튼 (또는 `/start`)
- 하단 메뉴 버튼
  - `📌 키워드 목록`
  - `➕ 키워드 추가`
  - `🗑 키워드 삭제`
  - `🧭 게시판 선택`
  - `❓ 도움말`

추가 기능:
- `,` 구분 다중 추가/삭제
  - `/add 햇반, 오레오, 폴햄`
  - `/remove 1,3,햇반`

## 백필(과거 6개월 1회 적재)
가격 비교 정확도를 높이려면 먼저 백필을 1회 수행하세요.

실행 예시
```bash
docker exec -it ppompu-keyword-bot python /app/backfill_6m.py --board-id ppomppu --months 6
```

드라이런
```bash
docker exec -it ppompu-keyword-bot python /app/backfill_6m.py --board-id ppomppu --months 6 --dry-run
```

추가 구간 실행 (예: 301~1000페이지)
```bash
docker exec -it ppompu-keyword-bot python /app/backfill_6m.py --board-id ppomppu --months 6 --start-page 301 --max-pages 1000
```

## 테스트
```bash
python -m unittest discover -s tests -v
python -m py_compile app.py db.py pricing.py backfill_6m.py
```

## 보안 주의
- `BOT_TOKEN`은 `docker-compose.yml`에 직접 넣지 말고 `.env` 사용 권장
- 토큰이 노출됐다면 `BotFather`에서 즉시 재발급(rotate)하세요
