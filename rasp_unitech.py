# rasp_unitech.py

import locale
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, filters, CallbackQueryHandler, ConversationHandler
)

from config import FEEDBACK_WAITING, DAY_SELECTION, CHANGE_GROUP_WAITING  # Added CHANGE_GROUP_WAITING
from logging_setup import setup_logging
from utils import load_api_key
from handlers import (
    start, info, change_command, feedback_start, feedback_receive, feedback_cancel,
    today_command, tomorrow_command, week_command, next_week_command, day_command,
    day_selection_start, day_selection, day_selection_text, handle_callback, text_handler, error_handler,
    change_start, change_receive  # Added change_start, change_receive
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

if __name__ == '__main__':
    logger.info("bot started", extra={'user_id': 'system', 'chat_id': 'system', 'username': 'unknown'})
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    
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
    app.add_handler(ConversationHandler(
        entry_points=[
            CallbackQueryHandler(change_start, pattern="^change$")
        ],
        states={
            CHANGE_GROUP_WAITING: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, change_receive),
                CommandHandler("cancel", feedback_cancel)
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
    
    app.run_polling(timeout=20, drop_pending_updates=True)