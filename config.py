import os
from dotenv import load_dotenv

load_dotenv()

# 필수 환경 변수
BOT_TOKEN = os.getenv("BOT_TOKEN")  # BotFather에서 받은 토큰
CHANNEL_ID = int(os.getenv("CHANNEL_ID"))  # 프라이빗 채널 ID (-100으로 시작하는 숫자)
ADMIN_USER_ID = int(os.getenv("ADMIN_USER_ID"))  # 너의 텔레그램 user_id

# Stripe 설정
STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET")  # Stripe 대시보드에서 생성

# PayPal 설정 (구독 자동 갱신 원하면)
PAYPAL_CLIENT_ID = os.getenv("PAYPAL_CLIENT_ID")
PAYPAL_SECRET = os.getenv("PAYPAL_SECRET")
PAYPAL_PLAN_ID = os.getenv("PAYPAL_PLAN_ID")  # PayPal에서 만든 월 구독 플랜 ID

# PostgreSQL (Render가 자동 제공)
DATABASE_URL = os.getenv("DATABASE_URL")

# 기타 설정
PRICE_MONTHLY_USD = 10  # $10
REMINDER_HOUR = 9  # 매일 오전 9시에 관리자에게 리포트 보냄 (UTC 기준 아님, Render 서버 시간)