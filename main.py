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

# 다국어 텍스트 (EN / AR / ES 완벽 지원)
TEXTS = {
    "EN": {
        "welcome": "👋 *Welcome to Premium Access Bot* 👋\n\n"
                   "We're thrilled to have you join us! 🎉\n\n"
                   "Unlock exclusive adult content, daily updates, and special perks in our private Telegram channel.\n\n"
                   "Choose your plan, complete payment, and get instant access via a secure invite link.\n\n"
                   "Our team is always here to support you 🤝\n\n"
                   "Welcome to the ultimate premium experience 🌟
                   
        ",
        "date_line": "\n📅 {date} — System Active
        
⚡️ Instant Access — ON",
        "plans_btn": "📦 View Plans",
        "status_btn": "📊 My Subscription",
        "help_btn": "❓ Help & Support",
        "select_plan": "🔥 *Choose Your Membership Plan* 🔥\n\n"
                       "Select the option that suits you best:",
        "monthly": "🔄 Monthly — $20/month",
        "lifetime": "💎 Lifetime — $50 ",
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
    },
    "AR": {
        "welcome": "👋 *مرحباً بك في بوت الوصول المميز* 👋\n\n"
                   "نحن سعداء جدًا بانضمامك إلينا! 🎉\n\n"
                   "احصل على وصول فوري إلى محتوى بالغين حصري، تحديثات يومية، ومميزات خاصة في قناتنا الخاصة على تليجرام.\n\n"
                   "اختر خطتك، أكمل الدفع، واحصل على رابط دعوة آمن فوراً.\n\n"
                   "فريقنا دائماً هنا لدعمك 🤝\n\n"
                   "مرحباً بك في التجربة المميزة المطلقة 🌟",
        "date_line": "\n📅 {date} — النظام نشط\n⚡️ الوصول الفوري — جاهز",
        "plans_btn": "📦 عرض الخطط",
        "status_btn": "📊 اشتراكي",
        "help_btn": "❓ المساعدة والدعم",
        "select_plan": "🔥 *اختر خطة العضوية* 🔥\n\n"
                       "اختر الخيار الذي يناسبك:",
        "monthly": "🔄 شهري — 20 دولار/شهر (تجديد تلقائي)",
        "lifetime": "💎 مدى الحياة — 50 دولار (دفعة واحدة دائمة)",
        "payment_method": "💳 *اختر طريقة الدفع*\n\n"
                          "لـ {plan} — كيف ترغب في الدفع؟",
        "stripe": "💳 Stripe (فوري وآمن)",
        "paypal": "🅿️ PayPal",
        "crypto": "₿ Crypto (USDT TRC20)",
        "stripe_redirect": "🔒 جاري التحويل إلى صفحة الدفع الآمنة Stripe...\n\n"
                           "سيتم تفعيل وصولك فوراً بعد الدفع.",
        "paypal_text": "*دفع PayPal — {plan}*\n\n"
                       "اضغط أدناه للذهاب إلى PayPal.\n\n"
                       "بعد الدفع، أرسل لقطة شاشة كإثبات للحصول على رابط الدعوة.",
        "crypto_text": "*دفع Crypto — USDT (TRC20)*\n\n"
                       "أرسل المبلغ الدقيق إلى العنوان التالي:\n\n"
                       "`TERhALhVLZRqnS3mZGhE1XgxyLnKHfgBLi`\n\n"
                       "أرسل إثبات المعاملة للحصول على الوصول فوراً.",
        "no_sub": "😔 لا يوجد اشتراك نشط.\n\n"
                  "جاهز لفتح المحتوى الحصري؟\nاختر خطة لبدء الرحلة!",
        "status_title": "📊 *حالة اشتراكك*",
        "plan": "الخطة",
        "payment_date": "تاريخ الدفع",
        "expires": "تنتهي في",
        "permanent": "وصول دائم",
        "manage_sub": "\nإدارة اشتراكك أدناه:",
        "help_text": "❓ *المساعدة والدعم*\n\n"
                     "• أسئلة الدفع → استخدم PayPal/Crypto وأرسل الإثبات\n"
                     "• عرض الحالة → زر اشتراكي\n"
                     "• تحتاج مساعدة → تواصل مع @mbrypie\n\n"
                     "نحن هنا 24/7 لمساعدتك! 🚀",
        "back": "⬅️ رجوع",
        "proof_here": "📤 أرسل الإثبات هنا",
        "pay_now": "💳 ادفع بـ Stripe",
        "pay_paypal": "💸 ادفع بـ PayPal"
    },
    "ES": {
        "welcome": "👋 *¡Bienvenido a Premium Access Bot!* 👋\n\n"
                   "¡Estamos emocionados de tenerte con nosotros! 🎉\n\n"
                   "Desbloquea contenido adulto exclusivo, actualizaciones diarias y beneficios especiales en nuestro canal privado de Telegram.\n\n"
                   "Elige tu plan, completa el pago y obtén acceso instantáneo mediante un enlace de invitación seguro.\n\n"
                   "Nuestro equipo siempre está aquí para apoyarte 🤝\n\n"
                   "¡Bienvenido a la experiencia premium definitiva 🌟",
        "date_line": "\n📅 {date} — Sistema Activo\n⚡️ Acceso Instantáneo — Listo",
        "plans_btn": "📦 Ver Planes",
        "status_btn": "📊 Mi Suscripción",
        "help_btn": "❓ Ayuda y Soporte",
        "select_plan": "🔥 *Elige Tu Plan de Membresía* 🔥\n\n"
                       "Selecciona la opción que mejor se adapte a ti:",
        "monthly": "🔄 Mensual — $20/mes (renovación automática)",
        "lifetime": "💎 De por vida — $50 (pago único permanente)",
        "payment_method": "💳 *Selecciona Método de Pago*\n\n"
                          "Para {plan} — ¿Cómo deseas pagar?",
        "stripe": "💳 Stripe (Instantáneo y Seguro)",
        "paypal": "🅿️ PayPal",
        "crypto": "₿ Crypto (USDT TRC20)",
        "stripe_redirect": "🔒 Redirigiendo a pago seguro de Stripe...\n\n"
                           "Tu acceso se activará inmediatamente después del pago.",
        "paypal_text": "*Pago PayPal — {plan}*\n\n"
                       "Haz clic abajo para ir a PayPal.\n\n"
                       "Después del pago, envía una captura de pantalla como comprobante para obtener tu enlace.",
        "crypto_text": "*Pago Crypto — USDT (TRC20)*\n\n"
                       "Envía la cantidad exacta a la dirección:\n\n"
                       "`TERhALhVLZRqnS3mZGhE1XgxyLnKHfgBLi`\n\n"
                       "Envía el comprobante de transacción para acceso instantáneo.",
        "no_sub": "😔 No se encontró suscripción activa.\n\n"
                  "¿Listo para desbloquear contenido exclusivo?\n¡Elige un plan para comenzar!",
        "status_title": "📊 *Estado de Tu Suscripción*",
        "plan": "Plan",
        "payment_date": "Fecha de Pago",
        "expires": "Expira",
        "permanent": "Acceso permanente",
        "manage_sub": "\nGestiona tu suscripción abajo:",
        "help_text": "❓ *Ayuda y Soporte*\n\n"
                     "• Problemas de pago → Usa PayPal/Crypto y envía comprobante\n"
                     "• Ver estado → Botón Mi Suscripción\n"
                     "• Necesitas ayuda → Contacta @mbrypie\n\n"
                     "¡Estamos aquí 24/7 para ayudarte! 🚀",
        "back": "⬅️ Atrás",
        "proof_here": "📤 Enviar Comprobante Aquí",
        "pay_now": "💳 Pagar con Stripe",
        "pay_paypal": "💸 Pagar con PayPal"
    }
}

def t(key, lang="EN", **kwargs):
    text = TEXTS.get(lang, TEXTS["EN"]).get(key, key)
    return text.format(**kwargs) if kwargs else text

async def get_user_language(user_id):
    conn = await asyncpg.connect(DATABASE_URL)
    row = await conn.fetchrow('SELECT language FROM members WHERE user_id = $1', user_id)
    await conn.close()
    return row['language'] if row and row['language'] else None

async def set_user_language(user_id, lang):
    conn = await asyncpg.connect(DATABASE_URL)
    await conn.execute('INSERT INTO members (user_id, language) VALUES ($1, $2) ON CONFLICT (user_id) DO UPDATE SET language = $2', user_id, lang)
    await conn.close()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    await log_action(user_id, 'start')

    lang = await get_user_language(user_id)

    if not lang:
        keyboard = [
            [InlineKeyboardButton("🇬🇧 English", callback_data='lang_en')],
            [InlineKeyboardButton("🇸🇦 العربية", callback_data='lang_ar')],
            [InlineKeyboardButton("🇪🇸 Español", callback_data='lang_es')]
        ]
        await update.message.reply_text(
            "🌍 Please select your preferred language:\n\n"
            "🇬🇧 English\n"
            "🇸🇦 العربية\n"
            "🇪🇸 Español",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    else:
        await show_main_menu(update, context, lang)

async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, lang: str):
    today = datetime.datetime.now(datetime.timezone.utc).strftime("%b %d")  # Python 3.12 호환

    text = t("welcome", lang) + t("date_line", lang, date=today)

    keyboard = [
        [InlineKeyboardButton(t("plans_btn", lang), callback_data='plans')],
        [InlineKeyboardButton(t("status_btn", lang), callback_data='status')],
        [InlineKeyboardButton(t("help_btn", lang), callback_data='help')]
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
    lang = await get_user_language(user_id) or "EN"

    if query.data.startswith('lang_'):
        new_lang = query.data.split('_')[1].upper()
        if new_lang not in TEXTS:
            new_lang = "EN"
        await set_user_language(user_id, new_lang)
        await query.edit_message_text(f"✅ Language changed to {new_lang}!")
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
        else:
            plan_text = "Lifetime 💎" if row['is_lifetime'] else "Monthly 🔄"
            payment_date = row['created_at'].strftime('%b %d, %Y')
            expire_text = "Permanent access" if row['is_lifetime'] else row['expiry'].strftime('%b %d, %Y')

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

    elif query.data == 'back_to_main':
        await show_main_menu(query, context, lang)

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
        username = session.get('customer_details', {}).get('email') or f"user_{user_id}"
        price_id = session['line_items']['data'][0]['price']['id']

        is_lifetime = (price_id == PRICE_ID_LIFETIME)
        amount = 50 if is_lifetime else 20

        asyncio.run(add_member(user_id, username, session.get('customer'), session.get('subscription'), is_lifetime))
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

