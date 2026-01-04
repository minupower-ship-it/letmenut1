import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHANNEL_ID = int(os.getenv("CHANNEL_ID"))
ADMIN_USER_ID = int(os.getenv("ADMIN_USER_ID"))

DATABASE_URL = os.getenv("DATABASE_URL")

STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET")

PRICE_ID_MONTHLY = os.getenv("PRICE_ID_MONTHLY")
PRICE_ID_LIFETIME = os.getenv("PRICE_ID_LIFETIME")

PORTAL_RETURN_URL = f"https://t.me/{os.getenv('BOT_USERNAME', 'yourbot')}"  # 봇 유저네임으로 변경 추천
SUCCESS_URL = PORTAL_RETURN_URL
CANCEL_URL = PORTAL_RETURN_URL
