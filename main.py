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
        "welcome": "\n👋 *Welcome to Premium Access Bot* 👋\n\n"
                   "We're thrilled to have you join us! 🎉\n\n"
                   "Unlock exclusive adult content, daily updates, and special perks in our private Telegram channel.\n\n"
                   "Choose your plan, complete payment, and get instant access via a secure invite link.\n\n"
                   "Our team is always here to support you 🤝\n\n"
                   "Welcome to the ultimate premium experience 🌟\n",
        "date_line": "\n\n📅 {date} — System Active\n⚡️ Instant Access — Ready",
        "plans_btn": "📦 View Plans",
        "status_btn": "📊 My Subscription",
        "help_btn": "❓ Help & Support",
        "select_plan": "🔥 *Choose Your Membership Plan* 🔥\n\n"
                       "Select the option that suits you best:",
        "monthly": "🔄 Monthly — $20/month",
        "lifetime": "💎 Lifetime — $50",
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
        "welcome": "\n👋 *مرحباً بك في بوت الوصول المميز* 👋\n\n"
                   "نحن سعداء جدًا بانضمامك إلينا! 🎉\n\n"
                   "احصل على وصول فوري إلى محتوى بالغين حصري، تحديثات يومية، ومميزات خاصة في قناتنا الخاصة على تليجرام.\n\n"
                   "اختر خطتك، أكمل الدفع، واحصل على رابط دعوة آمن فوراً.\n\n"
                   "فريقنا دائماً هنا لدعمك 🤝\n\n"
                   "مرحباً بك في التجربة المميزة المطلقة 🌟\n",
        "date_line": "\n\n📅 {date} — النظام نشط\n⚡️ الوصول الفوري — جاهز",
        "plans_btn": "📦 عرض الخطط",
        "status_btn": "📊 اشتراكي",
        "help_btn": "❓ المساعدة والدعم",
        "select_plan": "🔥 *اختر خطة العضوية* 🔥\n\n"
                       "اختر الخيار الذي يناسبك:",
        "monthly": "🔄 شهري — 20 دولار/شهر",
        "lifetime": "💎 مدى الحياة — 50 دولار",
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
        "welcome": "\n👋 *¡Bienvenido a Premium Access Bot!* 👋\n\n"
                   "¡Estamos emocionados de tenerte con nosotros! 🎉\n\n"
                   "Desbloquea contenido adulto exclusivo, actualizaciones diarias y beneficios especiales en nuestro canal privado de Telegram.\n\n"
                   "Elige tu plan, completa el pago y obtén acceso instantáneo mediante un enlace de invitación seguro.\n\n"
                   "Nuestro equipo siempre está aquí para apoyarte 🤝\n\n"
                   "¡Bienvenido a la experiencia premium definitiva 🌟\n",
        "date_line": "\n\n📅 {date} — Sistema Activo\n⚡️ Acceso Instantáneo — Listo",
        "plans_btn": "📦 Ver Planes",
        "status_btn": "📊 Mi Suscripción",
        "help_btn": "❓ Ayuda y Soporte",
        "select_plan": "🔥 *Elige Tu Plan de Membresía* 🔥\n\n"
                       "Selecciona la opción que mejor se adapte a ti:",
        "monthly": "🔄 Mensual — $20/mes",
        "lifetime": "💎 De por vida — $50",
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
    today = datetime.datetime.now(datetime.timezone.utc).strftime("%b %d")

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

# button_handler부터 main()까지는 이전과 완전히 동일 (변경 없음)

# (이전 버전의 button_handler, stripe_webhook, main 함수 그대로 사용)

if __name__ == '__main__':
    asyncio.run(main())
