import asyncio
import datetime
from datetime import timezone
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
    # AR, ES는 필요 시 추가 (현재 EN만으로도 충분)
}

def t(key, lang="EN", **kwargs):
    return TEXTS["EN"].get(key, key).format(**kwargs) if kwargs else TEXTS["EN"].get(key, key)

async def get_user_language(user_id):
    conn = await asyncpg.connect(DATABASE_URL)
    row = await conn.fetchrow('SELECT language FROM members WHERE user_id = $1', user_id)
    await conn.close()
    return row['language'] if row and row['language'] else "EN"

async def set_user_language(user_id, lang):
    conn = await asyncpg.connect(DATABASE_URL)
    await conn.execute('INSERT INTO members (user_id, language) VALUES ($1, $2) ON CONFLICT (user_id) DO UPDATE SET language = $2', user_id, lang)
    await conn.close()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    await log_action(user_id, 'start')

    lang = await get_user_language(user_id)

    if lang == "EN":  # 첫 방문이면 언어 선택 (임시로 EN만)
        keyboard = [
            [InlineKeyboardButton("🇬🇧 English", callback_data='lang_en')],
        ]
        await update.message.reply_text("🌍 Choose your preferred language:", reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        await show_main_menu(update, context, lang)

async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, lang: str):
    today = datetime.datetime.now(timezone.UTC).strftime("%b %d")

    text = t("welcome") + t("date_line", date=today)

    keyboard = [
        [InlineKeyboardButton(t("plans_btn"), callback_data='plans')],
        [InlineKeyboardButton(t("status_btn"), callback_data='status')],
        [InlineKeyboardButton(t("help_btn"), callback_data='help')]
    ]

    reply_markup = InlineKeyboardMarkup(keyboard)

    if update.message:
        await update.message.reply_text(text, parse_mode='Markdown', reply_markup=reply_markup)
    elif update.callback_query:
        await update.callback_query.edit_message_text(text, parse_mode='Markdown', reply_markup=reply_markup)

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    lang = await get_user_language(user_id)

    if query.data.startswith('lang_'):
        new_lang = "EN"
        await set_user_language(user_id, new_lang)
        await query.edit_message_text("Language set to English!")
        await show_main_menu(query, context, new_lang)
        return

    if query.data == 'plans':
        keyboard = [
            [InlineKeyboardButton(t("monthly"), callback_data='select_monthly')],
            [InlineKeyboardButton(t("lifetime"), callback_data='select_lifetime')],
            [InlineKeyboardButton(t("back"), callback_data='back_to_main')]
        ]
        await query.edit_message_text(t("select_plan"), parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(keyboard))

    elif query.data == 'status':
        row = await get_member_status(user_id)
        if not row:
            await query.edit_message_text(t("no_sub"), parse_mode='Markdown',
                                          reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(t("plans_btn"), callback_data='plans')]]))
        else:
            # 상태 표시 로직 (이전 코드와 동일)
            await query.edit_message_text("Subscription status display logic here", parse_mode='Markdown')

    elif query.data == 'help':
        await query.edit_message_text(t("help_text"), parse_mode='Markdown',
                                      reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(t("back"), callback_data='back_to_main')]]))

    elif query.data == 'back_to_main':
        await show_main_menu(query, context, lang)

@flask_app.route('/webhook/stripe', methods=['POST'])
def stripe_webhook():
    # 이전과 동일
    return '', 200

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
