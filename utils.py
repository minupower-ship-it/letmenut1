from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from config import CHANNEL_ID, ADMIN_USER_ID
from database import get_near_expiry, get_expired_today, get_overdue
import datetime

async def generate_invite_link(bot, user_id: int, months: int = 1):
    expiry = datetime.datetime.utcnow() + datetime.timedelta(days=30 * months)
    invite = await bot.create_chat_invite_link(
        chat_id=CHANNEL_ID,
        expire_date=expiry,
        member_limit=1
    )
    return invite.invite_link, expiry

async def send_daily_reminder(context: ContextTypes.DEFAULT_TYPE):
    today = datetime.datetime.utcnow().date()
    message = f"📊 멤버십 일일 리포트 ({today})\n\n"

    # 만료 임박 (1일, 3일 남음)
    soon = await get_near_expiry([1, 3])
    if soon:
        message += "🔴 만료 임박:\n"
        for _, username, days_left in soon:
            message += f"• @{username} — {days_left}일 남음\n"
        message += "\n"

    # 오늘 만료
    today_exp = await get_expired_today()
    if today_exp:
        message += "🟡 오늘 만료:\n"
        for _, username in today_exp:
            message += f"• @{username}\n"
        message += "\n"

    # 7일 이상 지난 사람
    overdue = await get_overdue(7)
    if overdue:
        message += "⚫ 만료 오래됨 (정리 고려):\n"
        for _, username in overdue:
            message += f"• @{username}\n"

    if not soon and not today_exp and not overdue:
        message += "🎉 오늘 만료된 사람 없어요! 모두 활성 중입니다."

    await context.bot.send_message(chat_id=ADMIN_USER_ID, text=message)