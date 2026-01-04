from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from config import CHANNEL_ID, ADMIN_USER_ID
from database import get_near_expiry, get_expired_today, get_daily_stats
import datetime

async def create_invite_link(bot):
    expire_date = datetime.datetime.utcnow() + datetime.timedelta(minutes=10)
    link = await bot.create_chat_invite_link(
        chat_id=CHANNEL_ID,
        expire_date=expire_date,
        member_limit=1
    )
    return link.invite_link, expire_date.strftime('%b %d, %Y %H:%M UTC')

async def send_daily_report(context: ContextTypes.DEFAULT_TYPE):
    today = datetime.datetime.utcnow().strftime("%b %d")
    stats = await get_daily_stats()
    near = await get_near_expiry()
    expired = await get_expired_today()

    message = f"📊 Daily Report - {today}\n\n"

    if near or expired:
        message += "🚨 Expiring Soon\n"
        for _, u, d in near:
            message += f"• @{u} - {d} days left\n"
        for _, u in expired:
            message += f"• @{u} - expires today\n"
        message += "\n"
    else:
        message += "✅ No expirations today\n\n"

    message += f"👥 Unique visitors: {stats['unique_users']}\n"
    message += f"💰 Revenue today: ${stats['total_revenue']:.2f}"

    await context.bot.send_message(ADMIN_USER_ID, message)
