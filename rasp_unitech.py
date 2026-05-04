# rasp_unitech.py

import locale
import sys
import os

from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, filters, CallbackQueryHandler, ConversationHandler
)
from telegram.request import HTTPXRequest

from config import FEEDBACK_WAITING, DAY_SELECTION, CHANGE_GROUP_WAITING, TEACHER_SELECT_WAITING, STUDENT_GROUP_WAITING
from src.logging_setup import setup_logging
from src.utils import load_api_key
from src.handlers import (
    start, info, change_command, feedback_start, feedback_receive, feedback_cancel,
    today_command, tomorrow_command, week_command, next_week_command, day_command,
    day_selection_start, day_selection, day_selection_text, handle_callback, text_handler, error_handler,
    change_start, change_receive, change_student_start, change_teacher_start,
    change_teacher_receive, teacher_select_receive
)

# Установка локали для русского языка
try:
    locale.setlocale(locale.LC_TIME, 'Russian_Russia.1251')
except locale.Error:
    try:
        locale.setlocale(locale.LC_TIME, 'ru_RU.UTF-8')
    except locale.Error:
        locale.setlocale(locale.LC_TIME, '')

logger = setup_logging()
TELEGRAM_TOKEN = load_api_key()


async def post_init(application):
    """Кэшируем username бота один раз при старте, чтобы не делать get_me() на каждое сообщение."""
    bot_info = await application.bot.get_me()
    application.bot_data['username'] = bot_info.username
    logger.info(
        "bot username cached: @%s", bot_info.username,
        extra={'user_id': 'system', 'chat_id': 'system', 'username': bot_info.username}
    )


if __name__ == '__main__':
    logger.info("bot started", extra={'user_id': 'system', 'chat_id': 'system', 'username': 'unknown'})

    # Увеличиваем пул соединений и таймауты, чтобы избежать PoolTimeout
    request = HTTPXRequest(
        connection_pool_size=8,
        pool_timeout=30.0,
        connect_timeout=15.0,
        read_timeout=15.0,
        write_timeout=15.0,
    )

    app = ApplicationBuilder().token(TELEGRAM_TOKEN).request(request).post_init(post_init).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("info", info))
    app.add_handler(CommandHandler("change", change_command))
    app.add_handler(ConversationHandler(
        entry_points=[
            CommandHandler("feedback", feedback_start),
            CallbackQueryHandler(feedback_start, pattern="^feedback$")
        ],
        states={
            FEEDBACK_WAITING: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, feedback_receive),
                CommandHandler("cancel", feedback_cancel)
            ],
        },
        fallbacks=[CommandHandler("cancel", feedback_cancel)],
        per_message=False
    ))
    app.add_handler(ConversationHandler(
        entry_points=[
            CommandHandler("day", day_selection_start),
            CallbackQueryHandler(day_selection_start, pattern="^day$")
        ],
        states={
            DAY_SELECTION: [
                CallbackQueryHandler(day_selection),
                MessageHandler(filters.TEXT & ~filters.COMMAND, day_selection_text)
            ],
        },
        fallbacks=[CommandHandler("cancel", feedback_cancel)],
        per_message=False
    ))
    # Отдельный обработчик для смены группы студента
    app.add_handler(ConversationHandler(
        entry_points=[
            CallbackQueryHandler(change_student_start, pattern="^change_student$")
        ],
        states={
            STUDENT_GROUP_WAITING: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, change_receive),
                CommandHandler("cancel", feedback_cancel)
            ],
        },
        fallbacks=[CommandHandler("cancel", feedback_cancel)],
        per_message=False
    ))
    # Отдельный обработчик для выбора преподавателя
    app.add_handler(ConversationHandler(
        entry_points=[
            CallbackQueryHandler(change_teacher_start, pattern="^change_teacher$")
        ],
        states={
            TEACHER_SELECT_WAITING: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, change_teacher_receive),
                CallbackQueryHandler(teacher_select_receive, pattern="^teacher_select_"),
                CommandHandler("cancel", feedback_cancel)
            ],
        },
        fallbacks=[CommandHandler("cancel", feedback_cancel)],
        per_message=False
    ))
    # Обработчик показа меню выбора студент/преподаватель
    app.add_handler(ConversationHandler(
        entry_points=[
            CallbackQueryHandler(change_start, pattern="^change$")
        ],
        states={
            CHANGE_GROUP_WAITING: [
                CallbackQueryHandler(change_student_start, pattern="^change_student$"),
                CallbackQueryHandler(change_teacher_start, pattern="^change_teacher$")
            ],
        },
        fallbacks=[CommandHandler("cancel", feedback_cancel)],
        per_message=False
    ))
    app.add_handler(CommandHandler("today", today_command))
    app.add_handler(CommandHandler("tomorrow", tomorrow_command))
    app.add_handler(CommandHandler("week", week_command))
    app.add_handler(CommandHandler("next_week", next_week_command))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
    app.add_error_handler(error_handler)

    app.run_polling(
        timeout=30,
        drop_pending_updates=True,
        pool_timeout=30.0,
    )
