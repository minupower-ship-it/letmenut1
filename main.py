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
application = None  # 전역으로 선언

@flask_app.route('/webhook/stripe', methods=['POST'])
def stripe_webhook():
    payload = request.data
    sig_header = request.headers.get('Stripe-Signature')
    try:
        event = stripe.Webhook.construct_event(payload, sig_header, STRIPE_WEBHOOK_SECRET)
    except:
        return abort(400)

    if event['type'] == 'checkout.session.completed':
        session = event['data']['object']
        user_id = int(session['metadata']['user_id'])
        username = session.get('customer_details', {}).get('email') or f"user_{user_id}"
        price_id = session['line_items']['data'][0]['price']['id']

        is_lifetime = (price_id == PRICE_ID_LIFETIME)
        amount = 100 if is_lifetime else 10

        asyncio.run(add_member(user_id, username, session['customer'], session.get('subscription'), is_lifetime))
        asyncio.run(log_action(user_id, 'payment_stripe_lifetime' if is_lifetime else 'payment_stripe_monthly', amount))

        invite_link, expire_time = asyncio.run(create_invite_link(application.bot))
        plan = "Lifetime 💎" if is_lifetime else "Monthly 🔄"

        asyncio.run(application.bot.send_message(
            user_id,
            f"🎉 {plan} Payment Successful!\n\n"
            f"Your private channel invite link (expires in 10 minutes):\n{invite_link}\n\n"
            f"Expires: {expire_time}\n"
            f"Enjoy the premium content! 🔥"
        ))

    elif event['type'] == 'customer.subscription.deleted':
        # 취소 자동 처리 (선택)
        pass

    return '', 200

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    await log_action(user_id, 'start')

    today = datetime.datetime.utcnow().strftime("%b %d")

    welcome_text = (
        "👋 Welcome to our Telegram Subscription Bot! 👋\n\n"
        "We’re glad to have you here 🎉\n\n"
        "With this bot, you can easily browse and subscribe to our premium plans designed to give you access to exclusive content, updates, and special offers through our private Telegram channels 📲✨\n\n"
        "Simply choose the plan that suits you best, and you’ll be added to the corresponding private channel. Stay connected, get the latest updates, and enjoy content shared with a like-minded community 🚀\n\n"
        "If you have any questions or need support, don’t hesitate to reach out — we’re always happy to help 🤝\n\n"
        "Enjoy exploring and welcome to the premium experience 🌟\n\n"
        f"📅 {today} - active\n"
        "⚡️ Immediate access - on"
    )

    keyboard = [
        [InlineKeyboardButton("📦 Subscribe", callback_data='subscribe')],
        [InlineKeyboardButton("📊 My Status", callback_data='status')],
        [InlineKeyboardButton("❓ Help", callback_data='help')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(welcome_text, reply_markup=reply_markup)

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    username = query.from_user.username or "unknown"

    if query.data == 'subscribe':
        keyboard = [
            [InlineKeyboardButton("🔄 Monthly ($10/month)", callback_data='monthly')],
            [InlineKeyboardButton("💎 Lifetime ($100)", callback_data='lifetime')],
            [InlineKeyboardButton("🅿️ PayPal Inquiry", callback_data='paypal')],
            [InlineKeyboardButton("₿ Crypto Inquiry", callback_data='crypto')],
            [InlineKeyboardButton("⬅️ Back", callback_data='back')]
        ]
        await query.edit_message_text(
            "🔥 Choose Your Premium Plan 🔥\n\n"
            "⚠️ Invite links expire in 10 minutes for security.",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    elif query.data in ['monthly', 'lifetime']:
        price_id = PRICE_ID_MONTHLY if query.data == 'monthly' else PRICE_ID_LIFETIME
        mode = 'subscription' if query.data == 'monthly' else 'payment'
        plan_name = "Monthly" if query.data == 'monthly' else "Lifetime"

        session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=[{'price': price_id, 'quantity': 1}],
            mode=mode,
            success_url=SUCCESS_URL,
            cancel_url=CANCEL_URL,
            metadata={'user_id': user_id}
        )
        await query.edit_message_text(
            f"Proceeding to {plan_name} payment via Stripe...",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("💳 Pay Now", url=session.url)]])
        )

    elif query.data in ['paypal', 'crypto']:
        method = "PayPal" if query.data == 'paypal' else "Crypto"
        await context.bot.send_message(ADMIN_USER_ID, f"{method} payment request from @{username} (ID: {user_id})")
        await query.edit_message_text(f"{method} request received! Admin will contact you soon 🚀")

    elif query.data == 'status':
        row = await get_member_status(user_id)
        if not row:
            await query.edit_message_text(
                "No active subscription found 😢\n\nStart your premium journey today!",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("📦 Subscribe", callback_data='subscribe')]])
            )
            return

        plan = "Lifetime 💎" if row['is_lifetime'] else "Monthly 🔄"
        payment_date = row['created_at'].strftime('%b %d, %Y')
        expire_text = "Permanent access" if row['is_lifetime'] else row['expiry'].strftime('%b %d, %Y')

        message = (
            f"📊 Your Subscription Status\n\n"
            f"Plan: {plan}\n"
            f"Payment Date: {payment_date}\n"
            f"Expires: {expire_text}\n\n"
            f"Manage your subscription below:"
        )

        keyboard = [[InlineKeyboardButton("⬅️ Back", callback_data='back')]]
        if row['stripe_customer_id']:
            portal = stripe.billing_portal.Session.create(
                customer=row['stripe_customer_id'],
                return_url=PORTAL_RETURN_URL
            )
            keyboard.insert(0, [InlineKeyboardButton("❌ Manage & Cancel Subscription", url=portal.url)])

        await query.edit_message_text(message, reply_markup=InlineKeyboardMarkup(keyboard))

    elif query.data == 'help':
        await query.edit_message_text(
            "❓ Help & Support\n\n"
            "• Payment issues → Use PayPal/Crypto inquiry\n"
            "• Check status → My Status button\n"
            "• Other questions → Message admin directly\n\n"
            "We're here to help! 🚀",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back", callback_data='back')]])
        )

    elif query.data == 'back':
        await start(update, context)

async def main():
    global application
    await init_db()

    application = Application.builder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(button_handler))

    application.job_queue.run_daily(send_daily_report, time=datetime.time(9, 0))

    import threading
    threading.Thread(target=lambda: flask_app.run(port=10000), daemon=True).start()

    print("Premium Bot is now running!")
    await application.start()
    await application.updater.start_polling()
    await asyncio.Event().wait()

if __name__ == '__main__':
    asyncio.run(main())
