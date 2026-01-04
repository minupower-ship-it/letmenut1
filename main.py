import asyncio
import datetime
import stripe
from flask import Flask, request, abort

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, PreCheckoutQueryHandler, MessageHandler, filters

from config import *
from database import init_db, add_or_update_subscription
from utils import generate_invite_link, send_daily_reminder

stripe.api_key = STRIPE_SECRET_KEY

# Flask 웹훅용 (Render에서 포트 10000 사용)
flask_app = Flask(__name__)

@flask_app.route('/webhook/stripe', methods=['POST'])
def stripe_webhook():
    payload = request.data
    sig_header = request.headers.get('Stripe-Signature')

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, STRIPE_WEBHOOK_SECRET)
    except Exception:
        return abort(400)

    if event['type'] == 'checkout.session.completed':
        session = event['data']['object']
        user_id = int(session['metadata']['user_id'])
        username = session.get('customer_details', {}).get('name') or f"stripe_{user_id}"

        invite_link, expiry = asyncio.run(generate_invite_link(application.bot, user_id))
        asyncio.run(add_or_update_subscription(user_id, username, method="stripe"))

        asyncio.run(application.bot.send_message(
            user_id,
            f"🎉 Stripe 결제 성공!\n\n"
            f"프리미엄 채널 초대 링크:\n{invite_link}\n\n"
            f"만료일: {expiry.strftime('%Y-%m-%d')}\n"
            f"재구독 잊지 마세요!"
        ))

    return '', 200

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("💳 Stripe로 결제 ($10/월)", callback_data='pay_stripe')],
        [InlineKeyboardButton("🅿️ PayPal로 결제", callback_data='pay_paypal')],
        [InlineKeyboardButton("₿ Crypto 결제 요청", callback_data='pay_crypto')],
        [InlineKeyboardButton("ℹ️ 이용 안내", callback_data='info')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "🔥 프리미엄 성인 채널 멤버십 🔥\n\n"
        "가격: $10 / 1개월\n"
        "결제 후 바로 1인용 초대 링크 드려요!\n"
        "언제든 재구독 가능합니다.",
        reply_markup=reply_markup
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    username = query.from_user.username or "unknown"

    if query.data == 'pay_stripe':
        session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=[{
                'price_data': {
                    'currency': 'usd',
                    'product_data': {'name': '프리미엄 채널 1개월'},
                    'unit_amount': PRICE_MONTHLY_USD * 100,
                },
                'quantity': 1,
            }],
            mode='payment',  # 한 번 결제 (구독은 복잡해지니 단순하게)
            success_url='https://yourdomain.onrender.com/success',
            cancel_url='https://yourdomain.onrender.com/cancel',
            metadata={'user_id': user_id}
        )
        keyboard = [[InlineKeyboardButton("💳 Stripe 결제하러 가기", url=session.url)]]
        await query.edit_message_text("Stripe 안전 결제 페이지로 이동합니다!", reply_markup=InlineKeyboardMarkup(keyboard))

    elif query.data == 'pay_paypal':
        await query.edit_message_text(
            "PayPal 결제를 원하시면 관리자에게 직접 문의해주세요!\n"
            "아래 명령어로 연락 주세요: /crypto (Crypto도 동일)"
        )

    elif query.data == 'pay_crypto':
        await context.bot.send_message(
            ADMIN_USER_ID,
            f"₿ 새 결제 요청!\n"
            f"유저: @{username} (ID: {user_id})\n"
            f"Stripe/PayPal/Crypto 중 하나로 처리 부탁!"
        )
        await query.edit_message_text("결제 요청 접수됐습니다! 🚀\n곧 관리자가 연락드릴게요.")

    elif query.data == 'info':
        await query.edit_message_text("ℹ️ 이용 안내\n\n- 결제 후 1인용 초대 링크 발급\n- 링크는 30일 후 만료\n- 재구독 시 새 링크 발급")

# 관리자 전용 명령어 (수동 링크 발급 등)
async def admin_extend(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id != ADMIN_USER_ID:
        return
    try:
        target_id = int(context.args[0])
        username = context.args[1] if len(context.args) > 1 else "manual"
        invite_link, expiry = await generate_invite_link(context.bot, target_id)
        await add_or_update_subscription(target_id, username, method="admin")
        await context.bot.send_message(target_id, f"관리자 연장! 🎉\n초대 링크: {invite_link}\n만료: {expiry.date()}")
        await update.message.reply_text(f"연장 완료: {target_id}")
    except:
        await update.message.reply_text("사용법: /extend user_id [username]")

async def main():
    await init_db()

    global application
    application = Application.builder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(CommandHandler("extend", admin_extend))  # 관리자용

    # 매일 리마인드
    application.job_queue.run_daily(send_daily_reminder, time=datetime.time(REMINDER_HOUR, 0))

    # Flask 웹훅과 함께 실행
    import threading
    threading.Thread(target=lambda: flask_app.run(port=10000, use_reloader=False), daemon=True).start()

    print("Bot is running...")
    await application.start()
    await application.updater.start_polling()
    await asyncio.Event().wait()

if __name__ == '__main__':
    asyncio.run(main())