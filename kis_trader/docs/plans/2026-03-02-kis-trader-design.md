# KIS 자동매매 시스템 설계 문서

**작성일:** 2026-03-02
**프로젝트:** kis_trader
**대상 API:** 한국투자증권 (Korea Investment & Securities) Open API

---

## 1. 개요

한국투자증권 Open API를 이용한 자동매매 웹 시스템.
모의투자 / 실전투자를 전환하며 사용하고, 동시호가 시간에는 사람이 웹 UI에서 직접 선택.

---

## 2. 기술 스택

| 항목 | 선택 |
|------|------|
| 백엔드 | Flask + APScheduler |
| DB | SQLite (SQLAlchemy) |
| 프론트엔드 | Jinja2 템플릿 + 바닐라 JS + SSE |
| KIS API | REST (OAuth2 토큰 방식) |
| ML | scikit-learn (RandomForest) |
| 포트 | 6000 |

---

## 3. 디렉터리 구조

```
kis_trader/
├── app.py                  # Flask 앱 팩토리 + APScheduler 등록
├── run.py                  # 서버 진입점
├── config.py               # 설정 (API 키, 모의/실전 URL, SQLite 경로)
├── kis_api.py              # 한국투자증권 REST API 래퍼
├── strategies/
│   ├── base.py             # 전략 기반 클래스
│   ├── ma_strategy.py      # 이동평균선 전략 (MA/EMA)
│   ├── rsi_macd.py         # RSI / MACD 전략
│   ├── condition.py        # 조건식 직접 설정 전략
│   └── ml_strategy.py      # AI/ML 예측 전략 (RandomForest)
├── scheduler.py            # APScheduler 작업 정의
├── db.py                   # SQLite ORM (SQLAlchemy)
├── routers/
│   ├── dashboard.py        # 대시보드 (잔고, 수익률, 실시간 체결)
│   ├── strategies.py       # 전략 CRUD
│   ├── orders.py           # 주문 내역
│   ├── auction.py          # 동시호가 팝업 (SSE + 수동 승인)
│   └── settings.py         # API 키, 모의/실전 전환
├── templates/
│   ├── base.html
│   ├── dashboard.html
│   ├── strategies.html
│   ├── orders.html
│   └── settings.html
└── static/
    └── js/auction.js       # SSE 수신 → 팝업 표시
```

---

## 4. DB 스키마

### strategies
```sql
CREATE TABLE strategies (
    id INTEGER PRIMARY KEY,
    name TEXT,
    stock_code TEXT,
    stock_name TEXT,
    strategy_type TEXT,       -- 'ma' | 'rsi_macd' | 'condition' | 'ml'
    params JSON,
    is_active BOOLEAN DEFAULT 1,
    mode TEXT DEFAULT 'paper', -- 'paper' | 'real'
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

### orders
```sql
CREATE TABLE orders (
    id INTEGER PRIMARY KEY,
    strategy_id INTEGER,
    stock_code TEXT,
    order_type TEXT,          -- 'buy' | 'sell'
    price REAL,
    quantity INTEGER,
    status TEXT,              -- 'pending' | 'submitted' | 'filled' | 'cancelled'
    trigger TEXT,             -- 'auto' | 'auction_manual'
    mode TEXT,
    kis_order_no TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

### auction_alerts
```sql
CREATE TABLE auction_alerts (
    id INTEGER PRIMARY KEY,
    strategy_id INTEGER,
    stock_code TEXT,
    stock_name TEXT,
    suggested_action TEXT,    -- 'buy' | 'sell'
    suggested_price REAL,
    suggested_qty INTEGER,
    user_decision TEXT,       -- NULL | 'buy' | 'sell' | 'pass'
    decided_at DATETIME,
    expires_at DATETIME,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

### portfolio_snapshots
```sql
CREATE TABLE portfolio_snapshots (
    id INTEGER PRIMARY KEY,
    mode TEXT,
    stock_code TEXT,
    quantity INTEGER,
    avg_price REAL,
    current_price REAL,
    snapped_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

---

## 5. 핵심 흐름

### 5-1. 일반 장중 자동매매 (1분마다)
1. APScheduler 1분 주기 실행
2. 활성화된 전략 목록 조회
3. 각 전략별 KIS API로 현재가 + 지표 계산
4. 조건 충족 시: KIS API 주문 전송 → orders 기록
5. SSE로 대시보드 실시간 갱신

### 5-2. 동시호가 처리 (08:00~09:00, 15:20~15:30)
1. APScheduler가 동시호가 시간 감지
2. 활성화된 전략 조건 점검 → 대상 종목 추출
3. auction_alerts INSERT (expires_at = 동시호가 마감)
4. SSE → 웹 클라이언트 팝업 표시
5. 사용자 선택(매수/매도/패스) → user_decision 업데이트
6. 매수/매도 선택 시: KIS API 호가 주문 → orders 기록
7. 미결정 시 expires_at 초과 → 자동 'pass' 처리

### 5-3. 모의/실전 전환
- settings 페이지에서 전환
- KIS API URL 자동 전환
  - 모의: `https://openapivts.koreainvestment.com:29443`
  - 실전: `https://openapi.koreainvestment.com:9443`
- 전략별 mode 개별 설정 가능

### 5-4. ML 전략
- 최근 60일 일봉 데이터로 RandomForest 학습
- 특성: MA5/20/60, RSI, MACD, 거래량비율
- 매일 새벽 03:00 자동 재학습

---

## 6. KIS API 주요 엔드포인트

| 기능 | TR ID (모의) | TR ID (실전) |
|------|-------------|-------------|
| 토큰 발급 | POST /oauth2/tokenP | 동일 |
| 현재가 조회 | FHKST01010100 | FHKST01010100 |
| 주식 매수 | VTTC0802U | TTTC0802U |
| 주식 매도 | VTTC0801U | TTTC0801U |
| 잔고 조회 | VTTC8434R | TTTC8434R |
| 체결 내역 | VTTC8001R | TTTC8001R |
| 일봉 조회 | FHKST03010100 | FHKST03010100 |

---

## 7. 전략 파라미터 예시

### MA 전략
```json
{
  "short_period": 5,
  "long_period": 20,
  "buy_qty": 10,
  "stop_loss_pct": -3.0,
  "take_profit_pct": 5.0
}
```

### RSI/MACD 전략
```json
{
  "rsi_period": 14,
  "rsi_oversold": 30,
  "rsi_overbought": 70,
  "macd_fast": 12,
  "macd_slow": 26,
  "macd_signal": 9,
  "buy_qty": 10
}
```

### 조건식 전략
```json
{
  "conditions": [
    {"indicator": "volume", "operator": ">", "value": 1000000},
    {"indicator": "change_pct", "operator": ">", "value": 3.0}
  ],
  "action": "buy",
  "buy_qty": 5
}
```

---

## 8. 웹 UI 페이지 구성

| 페이지 | URL | 주요 기능 |
|--------|-----|-----------|
| 대시보드 | / | 잔고, 수익률, 실시간 체결, 동시호가 팝업 |
| 전략 관리 | /strategies | 전략 추가/수정/삭제/활성화 |
| 주문 내역 | /orders | 자동/수동 주문 이력, 필터 |
| 설정 | /settings | API 키 입력, 모의/실전 전환, 토큰 갱신 |

---

## 9. 보안 고려사항

- API 키/시크릿은 DB에 암호화 저장 (Fernet)
- 실전 투자 전환 시 PIN 확인 절차
- 동시호가 주문은 사용자 확인 필수 (자동 주문 불가)
- 장 시간 외 주문 시도 차단

---

## 10. 향후 확장 (현재 범위 외)

- 텔레그램 알림 연동
- 멀티 계좌 지원
- 백테스팅 모듈
