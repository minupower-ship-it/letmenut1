import asyncio
import datetime
import stripe
from flask import Flask, request, abort

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

from config import *
from database import init_db, add_member, log_action, get_member_status
from utils import create_invite_link, send_daily_report

stripe.api_key = STRIPE_SECRET_KEY

flask_app = Flask(__name__)
application = None

# 다국어 텍스트 (여백과 단락을 넉넉히 넣어 가독성 UP)
TEXTS = {
    "EN": {
        "welcome": "👋 *Welcome to our Premium Subscription Bot!* 👋\n\n"
                   "We’re thrilled to have you here! 🎉\n\n"
                   "Get instant access to exclusive adult content, daily updates, and special perks through our private Telegram channel.\n\n"
                   "Choose a plan below, complete payment, and receive your private invite link immediately.\n\n"
                   "If you have any questions, we’re always here to help 🤝\n\n"
                   "Welcome to the premium experience 🌟",
        "date_line": "\n📅 {date} — System Active\n⚡️ Immediate Access — Enabled",
        "plans_btn": "📦 View Plans",
        "status_btn": "📊 My Subscription",
        "help_btn": "❓ Help & Support",
        "select_plan": "🔥 *Choose Your Membership Plan* 🔥\n\n"
                       "Select the option that best fits your needs:",
        "monthly": "🔄 Monthly Access — $20/month",
        "lifetime": "💎 Lifetime Access — $50 (one-time)",
        "payment_method": "💳 *Payment Method for {plan}*\n\n"
                          "How would you like to complete your purchase?",
        "stripe": "💳 Stripe (Instant & Automatic)",
        "paypal": "🅿️ PayPal",
        "crypto": "₿ Crypto (USDT TRC20)",
        "stripe_redirect": "🔒 Redirecting to secure Stripe checkout...\n\nYour access will be granted instantly upon completion.",
        "paypal_text": "*PayPal Payment — {plan}*\n\n"
                       "Click the button below to be redirected to PayPal.\n\n"
                       "After completing payment, please send proof (screenshot) to proceed.",
        "crypto_text": "*Crypto Payment — USDT (TRC20)*\n\n"
                       "Send the exact amount to the address below:\n\n"
                       "`TERhALhVLZRqnS3mZGhE1XgxyLnKHfgBLi`\n\n"
                       "After sending, forward the transaction proof to get instant access.",
        "no_sub": "😔 No active subscription found.\n\n"
                  "Ready to unlock premium content?\nChoose a plan below to get started!",
        "status_title": "📊 *Your Subscription Status*",
        "plan": "Plan",
        "payment_date": "Payment Date",
        "expires": "Expires",
        "permanent": "Permanent access",
        "manage_sub": "\nManage your subscription (cancel, update card, etc.):",
        "help_text": "❓ *Help & Support*\n\n"
                     "• Payment issues → Use PayPal or Crypto and send proof\n"
                     "• Check status → My Subscription button\n"
                     "• Questions or support → Contact @mbrypie directly\n\n"
                     "We’re here to help you enjoy the best experience! 🚀",
        "back": "⬅️ Back",
        "proof_here": "📤 Send Proof Here",
        "pay_now": "💳 Pay with Stripe",
        "pay_paypal": "💸 Pay with PayPal"
    },
    # AR과 ES는 필요시 추가 (현재 EN만으로도 충분히 예쁨)
    # 나중에 추가하고 싶으면 알려줘!
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

    if lang == "EN":  # 첫 방문이면 언어 선택 (현재 EN만 구현, 나중에 AR/ES 추가 가능)
        keyboard = [
            [InlineKeyboardButton("🇬🇧 English", callback_data='lang_en')],
            # [InlineKeyboardButton("🇸🇦 العربية", callback_data='lang_ar')],
            # [InlineKeyboardButton("🇪🇸 Español", callback_data='lang_es')]
        ]
        await update.message.reply_text("🌍 Select your preferred language:", reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        await show_main_menu(update, context, lang)

async def show_main_menu(update, context, lang):
    today = datetime.datetime.utcnow().strftime("%b %d")

    await update.message.reply_text(
        t("welcome", lang) + t("date_line", lang, date=today),
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton(t("plans_btn", lang), callback_data='plans')],
            [InlineKeyboardButton(t("status_btn", lang), callback_data='status')],
            [InlineKeyboardButton(t("help_btn", lang), callback_data='help')]
        ])
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    lang = await get_user_language(user_id)

    if query.data.startswith('lang_'):
        new_lang = "EN"  # 현재 EN만 지원
        await set_user_language(user_id, new_lang)
        await query.edit_message_text("✅ Language set to English!")
        await show_main_menu(query, context, new_lang)
        return

    if query.data == 'plans':
        keyboard = [
            [InlineKeyboardButton(t("monthly", lang), callback_data='select_monthly')],
            [InlineKeyboardButton(t("lifetime", lang), callback_data='select_lifetime')],
            [InlineKeyboardButton(t("back", lang), callback_data='back_to_main')]
        ]
        await query.edit_message_text(t("select_plan", lang), parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(keyboard))

    elif query.data in ['select_monthly', 'select_lifetime']:
        plan_name = "Monthly ($20)" if query.data == 'select_monthly' else "Lifetime ($50)"
        is_lifetime = query.data == 'select_lifetime'

        keyboard = [
            [InlineKeyboardButton(t("stripe", lang), callback_data=f'pay_stripe_{"lifetime" if is_lifetime else "monthly"}')],
            [InlineKeyboardButton(t("paypal", lang), callback_data=f'pay_paypal_{"lifetime" if is_lifetime else "monthly"}')],
            [InlineKeyboardButton(t("crypto", lang), callback_data=f'pay_crypto_{"lifetime" if is_lifetime else "monthly"}')],
            [InlineKeyboardButton(t("back", lang), callback_data='plans')]
        ]
        await query.edit_message_text(t("payment_method", lang, plan=plan_name), parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(keyboard))

    elif query.data.startswith('pay_stripe_'):
        plan_type = query.data.split('_')[2]
        price_id = PRICE_ID_MONTHLY if plan_type == 'monthly' else PRICE_ID_LIFETIME

        session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=[{'price': price_id, 'quantity': 1}],
            mode='subscription' if plan_type == 'monthly' else 'payment',
            success_url=SUCCESS_URL,
            cancel_url=CANCEL_URL,
            metadata={'user_id': user_id}
        )
        await query.edit_message_text(t("stripe_redirect", lang), parse_mode='Markdown',
                                      reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(t("pay_now", lang), url=session.url)]]))

    elif query.data.startswith('pay_paypal_'):
        plan_type = query.data.split('_')[2]
        plan_name = "Lifetime ($50)" if plan_type == 'lifetime' else "Monthly ($20)"
        paypal_link = "https://www.paypal.com/paypalme/minwookim384/50usd" if plan_type == 'lifetime' else "https://www.paypal.com/paypalme/minwookim384/20usd"

        keyboard = [
            [InlineKeyboardButton(t("pay_paypal", lang), url=paypal_link)],
            [InlineKeyboardButton(t("proof_here", lang), url="https://t.me/mbrypie")],
            [InlineKeyboardButton(t("back", lang), callback_data='plans')]
        ]
        await query.edit_message_text(t("paypal_text", lang, plan=plan_name), parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(keyboard))

    elif query.data.startswith('pay_crypto_'):
        qr_url = "https://files.catbox.moe/fkxh5l.png"
        caption = t("crypto_text", lang)

        await query.message.reply_photo(
            photo=qr_url,
            caption=caption,
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(t("proof_here", lang), url="https://t.me/mbrypie")],
                [InlineKeyboardButton(t("back", lang), callback_data='plans')]
            ])
        )
        await query.message.delete()

    elif query.data == 'status':
        row = await get_member_status(user_id)
        if not row:
            await query.edit_message_text(t("no_sub", lang), parse_mode='Markdown',
                                          reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(t("plans_btn", lang), callback_data='plans')]]))
            return

        plan_text = t("lifetime", lang) if row['is_lifetime'] else t("monthly", lang)
        payment_date = row['created_at'].strftime('%b %d, %Y')
        expire_text = t("permanent", lang) if row['is_lifetime'] else row['expiry'].strftime('%b %d, %Y')

        message = (
            f"{t('status_title', lang)}\n\n"
            f"{t('plan', lang)}: {plan_text}\n"
            f"{t('payment_date', lang)}: {payment_date}\n"
            f"{t('expires', lang)}: {expire_text}\n\n"
            f"{t('manage_sub', lang)}"
        )

        keyboard = [[InlineKeyboardButton(t("back", lang), callback_data='back_to_main')]]
        if row['stripe_customer_id']:
            portal = stripe.billing_portal.Session.create(customer=row['stripe_customer_id'], return_url=PORTAL_RETURN_URL)
            keyboard.insert(0, [InlineKeyboardButton("❌ Manage & Cancel", url=portal.url)])

        await query.edit_message_text(message, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(keyboard))

    elif query.data == 'help':
        await query.edit_message_text(t("help_text", lang), parse_mode='Markdown',
                                      reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(t("back", lang), callback_data='back_to_main')]]))

    elif query.data in ['back_to_main', 'back']:
        await show_main_menu(query, context, lang)

# 나머지 webhook, main 함수는 이전과 동일 (initialize, polling 등)

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
    threading.Thread(target=lambda: flask_app.run(port=10000), daemon=True).start()

    print("Premium Bot is now running with enhanced UX!")

    await asyncio.Event().wait()

if __name__ == '__main__':
    asyncio.run(main())
