import asyncio
import datetime
from datetime import timezone  # <-- 추가!
import stripe
import asyncpg
from flask import Flask, request, abort

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

from config import *
from database import init_db, add_member, log_action, get_member_status
from utils import create_invite_link, send_daily_report

stripe.api_key = STRIPE_SECRET_KEY

flask_app = Flask(__name__)
application = None

# 다국어 텍스트 (EN만으로도 충분히 예쁨, 필요시 AR/ES 추가)
TEXTS = {
    "EN": {
        "welcome": "👋 *Welcome to Premium Access Bot* 👋\n\n"
                   "We're thrilled to have you join us! 🎉\n\n"
                   "Unlock exclusive adult content, daily updates, and special perks in our private Telegram channel.\n\n"
                   "Choose your plan, complete payment, and get instant access via a secure invite link.\n\n"
                   "Our team is always here to support you 🤝\n\n"
                   "Welcome to the ultimate premium experience 🌟",
        "date_line": "\n📅 {date} — System Active\n⚡️ Instant Access — Ready",
        "plans_btn": "📦 View Plans",
        "status_btn": "📊 My Subscription",
        "help_btn": "❓ Help & Support",
        "select_plan": "🔥 *Choose Your Membership Plan* 🔥\n\n"
                       "Select the option that suits you best:",
        "monthly": "🔄 Monthly — $20/month (auto-renew)",
        "lifetime": "💎 Lifetime — $50 (one-time permanent)",
        "payment_method": "💳 *Select Payment Method*\n\n"
                          "For {plan} — How would you like to pay?",
        "stripe": "💳 Stripe (Instant & Secure)",
        "paypal": "🅿️ PayPal",
        "crypto": "₿ Crypto (USDT TRC20)",
        "stripe_redirect": "🔒 Redirecting to secure Stripe checkout...\n\n"
                           "Your access will be activated immediately after payment.",
        "paypal_text": "*PayPal Payment — {plan}*\n\n"
                       "Click below to go to PayPal.\n\n"
                       "After payment, send a screenshot as proof to get your invite link.",
        "crypto_text": "*Crypto Payment — USDT (TRC20)*\n\n"
                       "Send exact amount to:\n\n"
                       "`TERhALhVLZRqnS3mZGhE1XgxyLnKHfgBLi`\n\n"
                       "Forward transaction proof for instant access.",
        "no_sub": "😔 No active subscription found.\n\n"
                  "Ready to unlock exclusive content?\nChoose a plan to begin!",
        "status_title": "📊 *Your Subscription Status*",
        "plan": "Plan",
        "payment_date": "Payment Date",
        "expires": "Expires",
        "permanent": "Permanent access",
        "manage_sub": "\nManage your subscription below:",
        "help_text": "❓ *Help & Support*\n\n"
                     "• Payment questions → Use PayPal/Crypto and send proof\n"
                     "• View status → My Subscription button\n"
                     "• Need assistance → Contact @mbrypie\n\n"
                     "We're here 24/7 to help! 🚀",
        "back": "⬅️ Back",
        "proof_here": "📤 Send Proof Here",
        "pay_now": "💳 Pay with Stripe",
        "pay_paypal": "💸 Pay with PayPal"
    }
}

def t(key, lang="EN", **kwargs):
    text = TEXTS.get(lang, TEXTS["EN"]).get(key, TEXTS["EN"][key])
    return text.format(**kwargs) if kwargs else text

async def get_user_language(user_id):
    conn = await asyncpg.connect(DATABASE_URL)
    row = await conn.fetchrow('SELECT language FROM members WHERE user_id = $1', user_id)
    await conn.close()
    return row['language'] if row else "EN"

async def set_user_language(user_id, lang):
    conn = await asyncpg.connect(DATABASE_URL)
    await conn.execute('INSERT INTO members (user_id, language) VALUES ($1, $2) ON CONFLICT (user_id) DO UPDATE SET language = $2', user_id, lang)
    await conn.close()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    await log_action(user_id, 'start')

    lang = await get_user_language(user_id)

    # 첫 방문 시 언어 선택 (현재 EN만 완벽 지원)
    if lang == "EN" and not await get_member_status(user_id):
        keyboard = [
            [InlineKeyboardButton("🇬🇧 English", callback_data='lang_en')],
        ]
        await update.message.reply_text("🌍 Choose your preferred language:", reply_markup=InlineKeyboardMarkup(keyboard))
        return

    await show_main_menu(update, context, lang)

async def show_main_menu(update, context, lang):
    today = datetime.datetime.now(timezone.UTC).strftime("%b %d")  # <-- utcnow() 수정!

    text = t("welcome", lang) + t("date_line", lang, date=today)

    keyboard = [
        [InlineKeyboardButton(t("plans_btn", lang), callback_data='plans')],
        [InlineKeyboardButton(t("status_btn", lang), callback_data='status')],
        [InlineKeyboardButton(t("help_btn", lang), callback_data='help')]
    ]

    if update.message:
        await update.message.reply_text(text, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        await update.callback_query.edit_message_text(text, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(keyboard))

# button_handler, webhook 등 나머지 코드는 이전과 동일 (변경 없음)

async def main():
    global application
    await init_db()

    application = Application.builder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(button_handler))

    application.job_queue.run_daily(send_daily_report, time=datetime.time(9, 0))

    await application.initialize()
    await application.start()
    await application.updater.start_polling()

    import threading
    threading.Thread(target=lambda: flask_app.run(host='0.0.0.0', port=10000), daemon=True).start()

    print("Premium Bot is now running!")

    await asyncio.Event().wait()

if __name__ == '__main__':
    asyncio.run(main())
