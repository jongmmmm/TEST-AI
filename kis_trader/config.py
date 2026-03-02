import os
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

class Config:
    # 반드시 .env에 SECRET_KEY를 설정하세요 (프로덕션에서 이 기본값 사용 금지)
    SECRET_KEY = os.getenv("SECRET_KEY", "kis-trader-dev-only-change-in-production")
    SQLALCHEMY_DATABASE_URI = f"sqlite:///{os.path.join(BASE_DIR, 'kis_trader.db')}"
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # KIS API
    KIS_APP_KEY = os.getenv("KIS_APP_KEY", "")
    KIS_APP_SECRET = os.getenv("KIS_APP_SECRET", "")
    KIS_ACCOUNT_NO = os.getenv("KIS_ACCOUNT_NO", "")
    KIS_ACCOUNT_SUFFIX = os.getenv("KIS_ACCOUNT_SUFFIX", "01")

    # URL
    PAPER_BASE_URL = "https://openapivts.koreainvestment.com:29443"
    REAL_BASE_URL  = "https://openapi.koreainvestment.com:9443"

    # 스케줄러
    STRATEGY_INTERVAL_SECONDS = 60
    AUCTION_CHECK_INTERVAL_SECONDS = 30
