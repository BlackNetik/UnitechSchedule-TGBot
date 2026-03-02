# handlers.py

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
from datetime import datetime
import traceback

from config import BOT_VERSION, LAST_UPDATED, FEEDBACK_WAITING, DAY_SELECTION, TEACHER_SELECT_WAITING, STUDENT_GROUP_WAITING
from src.utils import load_users, save_users, MSK, logger
from src.keyboards import get_menu_keyboard, get_schedule_keyboard, get_day_selection_keyboard, get_change_group_keyboard
from src.schedule import download_ics, download_teacher_ics, parse_ics, get_today_schedule, get_tomorrow_schedule, get_week_schedule, get_next_week_schedule, get_day_schedule
from src.get_student_id import get_schedule, find_teacher

from config import CHANGE_GROUP_WAITING, DEVELOPER_CHAT_ID, DEVELOPER_USERNAME

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_key = f"{update.effective_chat.id}"
    users_data = load_users()
    if chat_key not in users_data:
        users_data[chat_key] = {'id_student': 90893}
        save_users(users_data)
    await update.message.reply_text(
        'Привет! 👋 Я бот, который поможет тебе узнать расписание занятий Технологического Университета им. А.А. Леонова с портала Unitech!\n'
        'По умолчанию показываю расписание для группы ПИ-23. Хочешь другую? Используй /change <название группы> (например, /change ПИ-23).\n'
        'Выбирай опции через кнопки или команды: /today, /tomorrow, /week, /next_week, /day, /info, /feedback.',
        reply_markup=get_menu_keyboard()
    )
    logger.info("sent start menu", extra={
        'user_id': update.effective_user.id,
        'chat_id': update.effective_chat.id,
        'username': update.effective_user.username or 'unknown'
    })

async def info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"Этот бот предоставляет расписание занятий на основе данных с портала Unitech.\n"
        f"Бот был написан сотрудником МОРС с помощью AI Grok\n"
        f"Расписание доступно для всех групп, используйте /change <название группы> для смены.\n"
        f"Дата создания: 01.09.2025. Текущая версия: {BOT_VERSION} от {LAST_UPDATED}\n"
        f"\nИспользуйте команды:\n"
        f"/today — расписание на сегодня\n"
        f"/tomorrow — расписание на завтра\n"
        f"/week — расписание на неделю\n"
        f"/next_week — расписание на следующую неделю\n"
        f"/day <номер_дня> — расписание на указанный день текущего месяца\n"
        f"/change — смена расписания\n"
        f"/feedback — отправить обратную связь разработчику",
        reply_markup=get_menu_keyboard()
    )
    logger.info("sent info", extra={
        'user_id': update.effective_user.id,
        'chat_id': update.effective_chat.id,
        'username': update.effective_user.username or 'unknown'
    })

async def change_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_key = f"{update.effective_chat.id}"
    users_data = load_users()
    if len(context.args) < 1:
        await update.message.reply_text(
            "Использование: /change <название группы> (например, /change ПИ-23)"
        )
        logger.info("invalid /change command: no group name provided", extra={
            'user_id': update.effective_user.id,
            'chat_id': update.effective_chat.id,
            'username': update.effective_user.username or 'unknown'
        })
        return
    
    group_name = ' '.join(context.args)
    try:
        student_id = get_schedule(group_name)
        if not student_id:
            await update.message.reply_text(
                f"Не удалось найти группу '{group_name}' или студентов в ней. Проверьте название и попробуйте снова.",
                reply_markup=get_menu_keyboard()
            )
            logger.info("failed to find group or student for group: %s", group_name, extra={
                'user_id': update.effective_user.id,
                'chat_id': update.effective_chat.id,
                'username': update.effective_user.username or 'unknown'
            })
            return
    except Exception as e:
        error_message = "Произошла ошибка при поиске группы. Пожалуйста, попробуйте еще раз."
        if "504" in str(e):
            error_message = "Сервер Unitech временно недоступен (ошибка 504). Пожалуйста, попробуйте снова через несколько минут."
        logger.info("failed to find group or student for group %s: %s", group_name, str(e), extra={
            'user_id': update.effective_user.id,
            'chat_id': update.effective_chat.id,
            'username': update.effective_user.username or 'unknown'
        })
        await update.message.reply_text(
            error_message,
            reply_markup=get_menu_keyboard()
        )
        return
    
    users_data[chat_key] = users_data.get(chat_key, {})
    users_data[chat_key]["id_student"] = student_id
    users_data[chat_key]["group_name"] = group_name
    save_users(users_data)
    await update.message.reply_text(
        f"Группа изменена на {group_name} (ID студента: {student_id})",
        reply_markup=get_menu_keyboard()
    )
    logger.info("changed group to %s (student ID: %s)", group_name, student_id, extra={
        'user_id': update.effective_user.id,
        'chat_id': update.effective_chat.id,
        'username': update.effective_user.username or 'unknown'
    })

async def feedback_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query:
        await update.callback_query.answer()
        try:
            if update.callback_query.message:
                await update.callback_query.message.delete()
        except Exception as e:
            logger.warning("failed to delete message in feedback_start: %s", str(e), extra={
                'user_id': update.effective_user.id,
                'chat_id': update.effective_chat.id,
                'username': update.effective_user.username or 'unknown'
            })
    
    try:
        await (update.message or update.callback_query.message).reply_text(
            "Пожалуйста, отправьте ваше сообщение для обратной связи."
        )
    except Exception as e:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="Пожалуйста, отправьте ваше сообщение для обратной связи."
        )
        logger.warning("failed to send feedback prompt: %s", str(e), extra={
            'user_id': update.effective_user.id,
            'chat_id': update.effective_chat.id,
            'username': update.effective_user.username or 'unknown'
        })
    
    logger.info("requested feedback message", extra={
        'user_id': update.effective_user.id,
        'chat_id': update.effective_chat.id,
        'username': update.effective_user.username or 'unknown'
    })
    return FEEDBACK_WAITING

async def feedback_receive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    feedback_text = update.message.text
    user_id = update.effective_user.id
    username = update.effective_user.username or 'unknown'
    chat_id = update.effective_chat.id
    
    logger.info("received feedback: %s", feedback_text, extra={
        'user_id': user_id,
        'chat_id': chat_id,
        'username': username
    })
    
    error_message = None
    try:
        await context.bot.send_message(
            chat_id=DEVELOPER_CHAT_ID,
            text=f"Обратная связь от пользователя @{username} (ID: {user_id}, Chat: {chat_id}):\n{feedback_text}"
        )
        logger.info("sent feedback to developer", extra={
            'user_id': user_id,
            'chat_id': chat_id,
            'username': username
        })
        await update.message.reply_text(
            "Спасибо за обратную связь! Она отправлена разработчику.",
            reply_markup=get_menu_keyboard()
        )
    except Exception as e:
        error_str = str(e)
        if "Chat not found" in error_str:
            error_message = f"Не удалось отправить обратную связь. Пожалуйста, свяжитесь с разработчиком напрямую: {DEVELOPER_USERNAME}"
            logger.error("failed to send feedback: Chat not found. DEVELOPER_CHAT_ID=%s may be invalid or bot was removed from the chat.", DEVELOPER_CHAT_ID, extra={
                'user_id': user_id,
                'chat_id': chat_id,
                'username': username
            })
        else:
            error_message = "Произошла ошибка при отправке обратной связи. Пожалуйста, попробуйте позже."
            logger.error("failed to send feedback: %s", error_str, extra={
                'user_id': user_id,
                'chat_id': chat_id,
                'username': username
            })
        
        await update.message.reply_text(
            error_message,
            reply_markup=get_menu_keyboard()
        )
    
    return ConversationHandler.END

async def feedback_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Отправка отзыва отменена.",
        reply_markup=get_menu_keyboard()
    )
    logger.info("feedback cancelled", extra={
        'user_id': update.effective_user.id,
        'chat_id': update.effective_chat.id,
        'username': update.effective_user.username or 'unknown'
    })
    return ConversationHandler.END

async def day_selection_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query:
        await update.callback_query.answer()
        try:
            if update.callback_query.message:
                await update.callback_query.message.delete()
        except Exception as e:
            logger.warning("failed to delete message in day_selection_start: %s", str(e), extra={
                'user_id': update.effective_user.id,
                'chat_id': update.effective_chat.id,
                'username': update.effective_user.username or 'unknown'
            })
    
    try:
        await (update.message or update.callback_query.message).reply_text(
            "Выберите день текущего месяца:",
            reply_markup=get_day_selection_keyboard(page=0)
        )
    except Exception as e:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="Выберите день текущего месяца:",
            reply_markup=get_day_selection_keyboard(page=0)
        )
        logger.warning("failed to send day selection prompt: %s", str(e), extra={
            'user_id': update.effective_user.id,
            'chat_id': update.effective_chat.id,
            'username': update.effective_user.username or 'unknown'
        })
    
    logger.info("started day selection", extra={
        'user_id': update.effective_user.id,
        'chat_id': update.effective_chat.id,
        'username': update.effective_user.username or 'unknown'
    })
    return DAY_SELECTION

async def day_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data.startswith("day_page_"):
        page = int(query.data.split("_")[-1])
        try:
            await query.message.edit_text(
                "Выберите день текущего месяца:",
                reply_markup=get_day_selection_keyboard(page=page)
            )
        except Exception as e:
            logger.warning("failed to edit day selection message: %s", str(e), extra={
                'user_id': update.effective_user.id,
                'chat_id': update.effective_chat.id,
                'username': update.effective_user.username or 'unknown'
            })
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="Выберите день текущего месяца:",
                reply_markup=get_day_selection_keyboard(page=page)
            )
        return DAY_SELECTION
    
    elif query.data.startswith("day_select_"):
        day = int(query.data.split("_")[-1])
        context.args = [str(day)]
        await day_command(update, context, query.message.chat_id)
        return ConversationHandler.END
    
    elif query.data == "menu":
        try:
            await query.message.edit_text(
                "Возвращаемся в главное меню.",
                reply_markup=get_menu_keyboard()
            )
        except Exception as e:
            logger.warning("failed to edit message to menu: %s", str(e), extra={
                'user_id': update.effective_user.id,
                'chat_id': update.effective_chat.id,
                'username': update.effective_user.username or 'unknown'
            })
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="Возвращаемся в главное меню.",
                reply_markup=get_menu_keyboard()
            )
        logger.info("returned to menu from day selection", extra={
            'user_id': update.effective_user.id,
            'chat_id': update.effective_chat.id,
            'username': update.effective_user.username or 'unknown'
        })
        return ConversationHandler.END

async def day_selection_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        day = int(update.message.text.strip())
        context.args = [str(day)]
        await day_command(update, context, update.message.chat_id)
        return ConversationHandler.END
    except ValueError:
        await update.message.reply_text(
            "Ошибка: номер дня должен быть числом (например, 17).",
            reply_markup=get_day_selection_keyboard(page=0)
        )
        logger.info("invalid day selection text: non-numeric input", extra={
            'user_id': update.effective_user.id,
            'chat_id': update.effective_chat.id,
            'username': update.effective_user.username or 'unknown'
        })
        return DAY_SELECTION

def get_schedule_events(chat_key):
    """Helper function to get events based on user type (student or teacher)"""
    users_data = load_users()
    user_data = users_data.get(chat_key, {})
    
    # Check if teacher mode is enabled
    if "id_teacher" in user_data:
        teacher_id = user_data["id_teacher"]
        ics_content = download_teacher_ics(teacher_id)
    else:
        student_id = user_data.get('id_student', 90893)
        ics_content = download_ics(student_id)
    
    events = parse_ics(ics_content)
    return events, user_data

async def today_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_key = f"{update.effective_chat.id}"
    
    try:
        events, user_data = get_schedule_events(chat_key)
        schedule, _ = get_today_schedule(events)
        
        user_type = "преподавателя" if "id_teacher" in user_data else "сегодня"
        await update.message.reply_text(
            f"Расписание для {user_type}:\n{schedule}",
            reply_markup=get_schedule_keyboard(exclude="today")
        )
        logger.info("sent today's schedule", extra={
            'user_id': update.effective_user.id,
            'chat_id': update.effective_chat.id,
            'username': update.effective_user.username or 'unknown'
        })
    except Exception as e:
        error_message = "Произошла ошибка при загрузке расписания. Пожалуйста, попробуйте еще раз."
        if "504" in str(e):
            error_message = "Сервер Unitech временно недоступен (ошибка 504). Пожалуйста, попробуйте снова через несколько минут."
        elif "Read timeout" in str(e):
            error_message = "Не удалось подключиться к серверу Unitech из-за таймаута. Проверьте интернет-соединение и попробуйте снова."
        await update.message.reply_text(
            error_message,
            reply_markup=get_schedule_keyboard(show_menu_button=True)
        )
        logger.error("failed to fetch today's schedule: %s", str(e), extra={
            'user_id': update.effective_user.id,
            'chat_id': update.effective_chat.id,
            'username': update.effective_user.username or 'unknown'
        })

async def tomorrow_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_key = f"{update.effective_chat.id}"
    
    try:
        events, user_data = get_schedule_events(chat_key)
        schedule, _ = get_tomorrow_schedule(events)
        
        user_type = "преподавателя" if "id_teacher" in user_data else "завтра"
        await update.message.reply_text(
            f"Расписание на {user_type}:\n{schedule}",
            reply_markup=get_schedule_keyboard(exclude="tomorrow")
        )
        logger.info("sent tomorrow's schedule", extra={
            'user_id': update.effective_user.id,
            'chat_id': update.effective_chat.id,
            'username': update.effective_user.username or 'unknown'
        })
    except Exception as e:
        error_message = "Произошла ошибка при загрузке расписания. Пожалуйста, попробуйте еще раз."
        if "504" in str(e):
            error_message = "Сервер Unitech временно недоступен (ошибка 504). Пожалуйста, попробуйте снова через несколько минут."
        elif "Read timeout" in str(e):
            error_message = "Не удалось подключиться к серверу Unitech из-за таймаута. Проверьте интернет-соединение и попробуйте снова."
        await update.message.reply_text(
            error_message,
            reply_markup=get_schedule_keyboard(show_menu_button=True)
        )
        logger.error("failed to fetch tomorrow's schedule: %s", str(e), extra={
            'user_id': update.effective_user.id,
            'chat_id': update.effective_chat.id,
            'username': update.effective_user.username or 'unknown'
        })

async def week_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_key = f"{update.effective_chat.id}"
    
    try:
        events, user_data = get_schedule_events(chat_key)
        schedule, _ = get_week_schedule(events)
        await update.message.reply_text(
            f"Расписание на неделю:\n{schedule}",
            reply_markup=get_schedule_keyboard(exclude="week")
        )
        logger.info("sent week's schedule", extra={
            'user_id': update.effective_user.id,
            'chat_id': update.effective_chat.id,
            'username': update.effective_user.username or 'unknown'
        })
    except Exception as e:
        error_message = "Произошла ошибка при загрузке расписания. Пожалуйста, попробуйте еще раз."
        if "504" in str(e):
            error_message = "Сервер Unitech временно недоступен (ошибка 504). Пожалуйста, попробуйте снова через несколько минут."
        elif "Read timeout" in str(e):
            error_message = "Не удалось подключиться к серверу Unitech из-за таймаута. Проверьте интернет-соединение и попробуйте снова."
        await update.message.reply_text(
            error_message,
            reply_markup=get_schedule_keyboard(show_menu_button=True)
        )
        logger.error("failed to fetch week's schedule: %s", str(e), extra={
            'user_id': update.effective_user.id,
            'chat_id': update.effective_chat.id,
            'username': update.effective_user.username or 'unknown'
        })

async def next_week_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_key = f"{update.effective_chat.id}"
    
    try:
        events, user_data = get_schedule_events(chat_key)
        schedule, _ = get_next_week_schedule(events)
        await update.message.reply_text(
            f"Расписание на следующую неделю:\n{schedule}",
            reply_markup=get_schedule_keyboard(exclude="next_week")
        )
        logger.info("sent next week's schedule", extra={
            'user_id': update.effective_user.id,
            'chat_id': update.effective_chat.id,
            'username': update.effective_user.username or 'unknown'
        })
    except Exception as e:
        error_message = "Произошла ошибка при загрузке расписания. Пожалуйста, попробуйте еще раз."
        if "504" in str(e):
            error_message = "Сервер Unitech временно недоступен (ошибка 504). Пожалуйста, попробуйте снова через несколько минут."
        elif "Read timeout" in str(e):
            error_message = "Не удалось подключиться к серверу Unitech из-за таймаута. Проверьте интернет-соединение и попробуйте снова."
        await update.message.reply_text(
            error_message,
            reply_markup=get_schedule_keyboard(show_menu_button=True)
        )
        logger.error("failed to fetch next week's schedule: %s", str(e), extra={
            'user_id': update.effective_user.id,
            'chat_id': update.effective_chat.id,
            'username': update.effective_user.username or 'unknown'
        })

async def day_command(update: Update, context: ContextTypes.DEFAULT_TYPE, chat_id: int):
    chat_key = f"{chat_id}"
    
    if len(context.args) < 1:
        try:
            await (update.message or update.callback_query.message).reply_text(
                "Выберите день текущего месяца:",
                reply_markup=get_day_selection_keyboard(page=0)
            )
        except Exception as e:
            await context.bot.send_message(
                chat_id=chat_id,
                text="Выберите день текущего месяца:",
                reply_markup=get_day_selection_keyboard(page=0)
            )
            logger.warning("failed to send day selection prompt in day_command: %s", str(e), extra={
                'user_id': update.effective_user.id,
                'chat_id': chat_id,
                'username': update.effective_user.username or 'unknown'
            })
        logger.info("day command without arguments, showing day selection", extra={
            'user_id': update.effective_user.id,
            'chat_id': chat_id,
            'username': update.effective_user.username or 'unknown'
        })
        return DAY_SELECTION
    
    try:
        day = int(context.args[0])
        events, user_data = get_schedule_events(chat_key)
        schedule, _ = get_day_schedule(events, day)
        try:
            await (update.message or update.callback_query.message).reply_text(
                f"Расписание на {day} число:\n{schedule}",
                reply_markup=get_schedule_keyboard(exclude="day")
            )
        except Exception as e:
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"Расписание на {day} число:\n{schedule}",
                reply_markup=get_schedule_keyboard(exclude="day")
            )
            logger.warning("failed to reply in day_command, sent new message: %s", str(e), extra={
                'user_id': update.effective_user.id,
                'chat_id': chat_id,
                'username': update.effective_user.username or 'unknown'
            })
        logger.info("sent schedule for day %s", day, extra={
            'user_id': update.effective_user.id,
            'chat_id': chat_id,
            'username': update.effective_user.username or 'unknown'
        })
    except ValueError:
        try:
            await (update.message or update.callback_query.message).reply_text(
                "Ошибка: номер дня должен быть числом (например, /day 17)",
                reply_markup=get_day_selection_keyboard(page=0)
            )
        except Exception as e:
            await context.bot.send_message(
                chat_id=chat_id,
                text="Ошибка: номер дня должен быть числом (например, /day 17)",
                reply_markup=get_day_selection_keyboard(page=0)
            )
            logger.warning("failed to reply in day_command for ValueError, sent new message: %s", str(e), extra={
                'user_id': update.effective_user.id,
                'chat_id': chat_id,
                'username': update.effective_user.username or 'unknown'
            })
        logger.info("invalid day command: non-numeric day provided", extra={
            'user_id': update.effective_user.id,
            'chat_id': chat_id,
            'username': update.effective_user.username or 'unknown'
        })
    except Exception as e:
        error_message = "Произошла ошибка при загрузке расписания. Пожалуйста, попробуйте еще раз."
        if "504" in str(e):
            error_message = "Сервер Unitech временно недоступен (ошибка 504). Пожалуйста, попробуйте снова через несколько минут."
        elif "Read timeout" in str(e):
            error_message = "Не удалось подключиться к серверу Unitech из-за таймаута. Проверьте интернет-соединение и попробуйте снова."
        try:
            await (update.message or update.callback_query.message).reply_text(
                error_message,
                reply_markup=get_schedule_keyboard(show_menu_button=True)
            )
        except Exception as e:
            await context.bot.send_message(
                chat_id=chat_id,
                text=error_message,
                reply_markup=get_schedule_keyboard(show_menu_button=True)
            )
            logger.warning("failed to reply in day_command for error, sent new message: %s", str(e), extra={
                'user_id': update.effective_user.id,
                'chat_id': chat_id,
                'username': update.effective_user.username or 'unknown'
            })
        logger.error("failed to fetch day schedule: %s", str(e), extra={
            'user_id': update.effective_user.id,
            'chat_id': chat_id,
            'username': update.effective_user.username or 'unknown'
        })

async def send_message(query, context, text, reply_markup=None):
    try:
        await query.message.reply_text(text, reply_markup=reply_markup)
    except Exception as e:
        logger.warning("failed to reply to message: %s, sending new message", str(e), extra={
            'user_id': query.from_user.id,
            'chat_id': query.message.chat_id,
            'username': query.from_user.username or 'unknown'
        })
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text=text,
            reply_markup=reply_markup
        )

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    try:
        if query.message:
            await query.message.delete()
    except Exception as e:
        logger.warning("failed to delete message in handle_callback: %s", str(e), extra={
            'user_id': update.effective_user.id,
            'chat_id': update.effective_chat.id,
            'username': update.effective_user.username or 'unknown'
        })

    if query.data == "menu":
        try:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="Возвращаемся в главное меню.",
                reply_markup=get_menu_keyboard()
            )
        except Exception as e:
            logger.warning("failed to send menu message: %s", str(e), extra={
                'user_id': update.effective_user.id,
                'chat_id': update.effective_chat.id,
                'username': update.effective_user.username or 'unknown'
            })
        logger.info("returned to menu via callback", extra={
            'user_id': update.effective_user.id,
            'chat_id': update.effective_chat.id,
            'username': update.effective_user.username or 'unknown'
        })
        return
    
    # Handle student/teacher selection callbacks
    if query.data == "change_student":
        await change_student_start(update, context)
        return
    elif query.data == "change_teacher":
        await change_teacher_start(update, context)
        return
    elif query.data.startswith("teacher_select_"):
        await teacher_select_receive(update, context)
        return
    
    chat_key = f"{update.effective_chat.id}"
    
    try:
        events, user_data = get_schedule_events(chat_key)
        
        if query.data == "today":
            schedule, _ = get_today_schedule(events)
            user_type = "преподавателя" if "id_teacher" in user_data else "сегодня"
            await send_message(
                query, context,
                f"Расписание для {user_type}:\n{schedule}",
                reply_markup=get_schedule_keyboard(exclude="today")
            )
            logger.info("sent today's schedule via callback", extra={
                'user_id': update.effective_user.id,
                'chat_id': update.effective_chat.id,
                'username': update.effective_user.username or 'unknown'
            })
        elif query.data == "tomorrow":
            schedule, _ = get_tomorrow_schedule(events)
            user_type = "преподавателя" if "id_teacher" in user_data else "завтра"
            await send_message(
                query, context,
                f"Расписание на {user_type}:\n{schedule}",
                reply_markup=get_schedule_keyboard(exclude="tomorrow")
            )
            logger.info("sent tomorrow's schedule via callback", extra={
                'user_id': update.effective_user.id,
                'chat_id': update.effective_chat.id,
                'username': update.effective_user.username or 'unknown'
            })
        elif query.data == "week":
            schedule, _ = get_week_schedule(events)
            await send_message(
                query, context,
                f"Расписание на неделю:\n{schedule}",
                reply_markup=get_schedule_keyboard(exclude="week")
            )
            logger.info("sent week's schedule via callback", extra={
                'user_id': update.effective_user.id,
                'chat_id': update.effective_chat.id,
                'username': update.effective_user.username or 'unknown'
            })
        elif query.data == "next_week":
            schedule, _ = get_next_week_schedule(events)
            await send_message(
                query, context,
                f"Расписание на следующую неделю:\n{schedule}",
                reply_markup=get_schedule_keyboard(exclude="next_week")
            )
            logger.info("sent next week's schedule via callback", extra={
                'user_id': update.effective_user.id,
                'chat_id': update.effective_chat.id,
                'username': update.effective_user.username or 'unknown'
            })
        elif query.data == "change":
            logger.info("change group button pressed", extra={
                'user_id': update.effective_user.id,
                'chat_id': update.effective_chat.id,
                'username': update.effective_user.username or 'unknown'
            })
            return
    except Exception as e:
        error_message = "Произошла ошибка при загрузке расписания. Пожалуйста, попробуйте еще раз."
        if "504" in str(e):
            error_message = "Сервер Unitech временно недоступен (ошибка 504). Пожалуйста, попробуйте снова через несколько минут."
        elif "Read timeout" in str(e):
            error_message = "Не удалось подключиться к серверу Unitech из-за таймаута. Проверьте интернет-соединение и попробуйте снова."
        await send_message(
            query, context,
            error_message,
            reply_markup=get_schedule_keyboard(show_menu_button=True)
        )
        logger.error("failed to process callback %s: %s", query.data, str(e), extra={
            'user_id': update.effective_user.id,
            'chat_id': update.effective_chat.id,
            'username': update.effective_user.username or 'unknown'
        })

# Change group/teacher handlers
async def change_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
        try:
            if query.message:
                await query.message.delete()
        except Exception as e:
            logger.warning("failed to delete message in change_start: %s", str(e), extra={
                'user_id': update.effective_user.id,
                'chat_id': update.effective_chat.id,
                'username': update.effective_user.username or 'unknown'
            })
    
    await (update.message or query.message).reply_text(
        "Выберите тип: студент или преподаватель?",
        reply_markup=get_change_group_keyboard()
    )
    logger.info("started group/teacher change", extra={
        'user_id': update.effective_user.id,
        'chat_id': update.effective_chat.id,
        'username': update.effective_user.username or 'unknown'
    })
    return CHANGE_GROUP_WAITING

async def change_receive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle student group name input"""
    group_name = update.message.text.strip()
    chat_key = f"{update.effective_chat.id}"
    users_data = load_users()
    
    try:
        student_id = get_schedule(group_name)
        if not student_id:
            await update.message.reply_text(
                f"Не удалось найти группу '{group_name}' или студентов в ней. Проверьте название и попробуйте снова.",
                reply_markup=get_menu_keyboard()
            )
            logger.info("failed to find group or student for group: %s", group_name, extra={
                'user_id': update.effective_user.id,
                'chat_id': update.effective_chat.id,
                'username': update.effective_user.username or 'unknown'
            })
            return ConversationHandler.END
        
        users_data[chat_key] = users_data.get(chat_key, {})
        users_data[chat_key]["id_student"] = student_id
        users_data[chat_key]["group_name"] = group_name
        # Clear teacher data when switching to student mode
        if "id_teacher" in users_data[chat_key]:
            del users_data[chat_key]["id_teacher"]
        if "teacher_name" in users_data[chat_key]:
            del users_data[chat_key]["teacher_name"]
        save_users(users_data)
        await update.message.reply_text(
            f"Группа изменена на {group_name} (ID студента: {student_id})",
            reply_markup=get_menu_keyboard()
        )
        logger.info("changed group to %s (student ID: %s)", group_name, student_id, extra={
            'user_id': update.effective_user.id,
            'chat_id': update.effective_chat.id,
            'username': update.effective_user.username or 'unknown'
        })
    except Exception as e:
        error_message = "Произошла ошибка при поиске группы. Пожалуйста, попробуйте еще раз."
        if "504" in str(e):
            error_message = "Сервер Unitech временно недоступен (ошибка 504). Пожалуйста, попробуйте снова через несколько минут."
        logger.error("failed to change group %s: %s", group_name, str(e), extra={
            'user_id': update.effective_user.id,
            'chat_id': update.effective_chat.id,
            'username': update.effective_user.username or 'unknown'
        })
        await update.message.reply_text(
            error_message,
            reply_markup=get_menu_keyboard()
        )
    
    return ConversationHandler.END

# Teacher selection handlers
async def change_student_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle 'Я студент' button - asks for group name"""
    query = update.callback_query
    if query:
        await query.answer()
        try:
            if query.message:
                await query.message.delete()
        except Exception as e:
            logger.warning("failed to delete message in change_student_start: %s", str(e), extra={
                'user_id': update.effective_user.id,
                'chat_id': update.effective_chat.id,
                'username': update.effective_user.username or 'unknown'
            })
    
    await (update.message or query.message).reply_text(
        "Пожалуйста, введите название группы (например, ПИ-23)."
    )
    logger.info("started student group change", extra={
        'user_id': update.effective_user.id,
        'chat_id': update.effective_chat.id,
        'username': update.effective_user.username or 'unknown'
    })
    return STUDENT_GROUP_WAITING  # Return different state for student

async def change_teacher_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle 'Я преподаватель' button - asks for teacher name"""
    query = update.callback_query
    if query:
        await query.answer()
        try:
            if query.message:
                await query.message.delete()
        except Exception as e:
            logger.warning("failed to delete message in change_teacher_start: %s", str(e), extra={
                'user_id': update.effective_user.id,
                'chat_id': update.effective_chat.id,
                'username': update.effective_user.username or 'unknown'
            })
    
    await (update.message or query.message).reply_text(
        "Введите имя преподавателя (например, Иван или Петров А.С.):"
    )
    logger.info("started teacher change, returning TEACHER_SELECT_WAITING=%s", TEACHER_SELECT_WAITING, extra={
        'user_id': update.effective_user.id,
        'chat_id': update.effective_chat.id,
        'username': update.effective_user.username or 'unknown'
    })
    return TEACHER_SELECT_WAITING

async def change_teacher_receive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle teacher name input and search for teachers"""
    teacher_name = update.message.text.strip()
    chat_key = f"{update.effective_chat.id}"
    users_data = load_users()
    
    try:
        teachers = find_teacher(teacher_name)
        
        if not teachers:
            await update.message.reply_text(
                f"Преподаватель '{teacher_name}' не найден. Попробуйте ввести другое имя или часть имени.",
                reply_markup=get_menu_keyboard()
            )
            logger.info("teacher not found: %s", teacher_name, extra={
                'user_id': update.effective_user.id,
                'chat_id': update.effective_chat.id,
                'username': update.effective_user.username or 'unknown'
            })
            return ConversationHandler.END
        
        if len(teachers) > 1:
            keyboard = []
            for teacher in teachers[:10]:
                keyboard.append([InlineKeyboardButton(teacher['name'], callback_data=f"teacher_select_{teacher['id']}")])
            keyboard.append([InlineKeyboardButton("Отмена", callback_data="menu")])
            
            await update.message.reply_text(
                f"Найдено несколько преподавателей. Выберите нужного:",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            logger.info("multiple teachers found for %s: %d matches", teacher_name, len(teachers), extra={
                'user_id': update.effective_user.id,
                'chat_id': update.effective_chat.id,
                'username': update.effective_user.username or 'unknown'
            })
            return TEACHER_SELECT_WAITING
        
        teacher = teachers[0]
        teacher_id = teacher['id']
        teacher_name_full = teacher['name']
        
        users_data[chat_key] = users_data.get(chat_key, {})
        users_data[chat_key]["id_teacher"] = teacher_id
        users_data[chat_key]["teacher_name"] = teacher_name_full
        if "id_student" in users_data[chat_key]:
            del users_data[chat_key]["id_student"]
        if "group_name" in users_data[chat_key]:
            del users_data[chat_key]["group_name"]
        save_users(users_data)
        
        await update.message.reply_text(
            f"Выбран преподаватель: {teacher_name_full} (ID: {teacher_id})",
            reply_markup=get_menu_keyboard()
        )
        logger.info("changed teacher to %s (ID: %s)", teacher_name_full, teacher_id, extra={
            'user_id': update.effective_user.id,
            'chat_id': update.effective_chat.id,
            'username': update.effective_user.username or 'unknown'
        })
        
    except Exception as e:
        error_message = "Произошла ошибка при поиске преподавателя. Пожалуйста, попробуйте еще раз."
        if "504" in str(e):
            error_message = "Сервер Unitech временно недоступен (ошибка 504). Пожалуйста, попробуйте снова через несколько минут."
        logger.error("failed to find teacher %s: %s", teacher_name, str(e), extra={
            'user_id': update.effective_user.id,
            'chat_id': update.effective_chat.id,
            'username': update.effective_user.username or 'unknown'
        })
        await update.message.reply_text(
            error_message,
            reply_markup=get_menu_keyboard()
        )
    
    return ConversationHandler.END

async def teacher_select_receive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle teacher selection from list when multiple matches found"""
    query = update.callback_query
    await query.answer()
    
    if query.data.startswith("teacher_select_"):
        teacher_id = int(query.data.split("_")[-1])
        chat_key = f"{update.effective_chat.id}"
        users_data = load_users()
        
        teachers = find_teacher("")
        teacher_name = ""
        for t in teachers:
            if t['id'] == teacher_id:
                teacher_name = t['name']
                break
        
        users_data[chat_key] = users_data.get(chat_key, {})
        users_data[chat_key]["id_teacher"] = teacher_id
        users_data[chat_key]["teacher_name"] = teacher_name
        if "id_student" in users_data[chat_key]:
            del users_data[chat_key]["id_student"]
        if "group_name" in users_data[chat_key]:
            del users_data[chat_key]["group_name"]
        save_users(users_data)
        
        try:
            await query.message.edit_text(
                f"Выбран преподаватель: {teacher_name} (ID: {teacher_id})",
                reply_markup=get_menu_keyboard()
            )
        except Exception:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=f"Выбран преподаватель: {teacher_name} (ID: {teacher_id})",
                reply_markup=get_menu_keyboard()
            )
        
        logger.info("selected teacher from list: %s (ID: %s)", teacher_name, teacher_id, extra={
            'user_id': update.effective_user.id,
            'chat_id': update.effective_chat.id,
            'username': update.effective_user.username or 'unknown'
        })
        
        return ConversationHandler.END
    
    return TEACHER_SELECT_WAITING

async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if update.effective_chat.type in ['group', 'supergroup']:
        bot_username = (await context.bot.get_me()).username
        if not (text.startswith(bot_username) or (update.message.reply_to_message and update.message.reply_to_message.from_user.id == context.bot.id)):
            return
        text = text.replace(bot_username, '').strip()
    
    if text in ["Расп. на сегодня", "Расписание на сегодня"]:
        await today_command(update, context)
    elif text in ["Расп. на завтра", "Расписание на завтра"]:
        await tomorrow_command(update, context)
    elif text in ["Расп. на неделю", "Расписание на неделю"]:
        await week_command(update, context)
    elif text in ["Расп. на след. неделю", "Расписание на следующую неделю"]:
        await next_week_command(update, context)
    elif text.startswith("Расп. на день ") or text.startswith("Расписание на день "):
        try:
            day = int(text.split()[-1])
            context.args = [str(day)]
            await day_command(update, context, update.message.chat_id)
        except ValueError:
            await update.message.reply_text(
                "Ошибка: номер дня должен быть числом (например, Расп. на день 17)",
                reply_markup=get_day_selection_keyboard(page=0)
            )
            logger.info("invalid text day command: non-numeric day provided", extra={
                'user_id': update.effective_user.id,
                'chat_id': update.effective_chat.id,
                'username': update.effective_user.username or 'unknown'
            })
    else:
        await update.message.reply_text(
            "Пожалуйста, используйте кнопки или команды /today, /tomorrow, /week, /next_week, /day, /info, /feedback.",
            reply_markup=get_menu_keyboard()
        )
        logger.info("received invalid text: %s", text, extra={
            'user_id': update.effective_user.id,
            'chat_id': update.effective_chat.id,
            'username': update.effective_user.username or 'unknown'
        })
    logger.info("processed text: %s", text, extra={
        'user_id': update.effective_user.id,
        'chat_id': update.effective_chat.id,
        'username': update.effective_user.username or 'unknown'
    })

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    error_message = "Произошла неизвестная ошибка. Пожалуйста, попробуйте еще раз."
    error_str = str(context.error) if context.error else "None"
    if "504" in error_str:
        error_message = "Сервер Unitech временно недоступен (ошибка 504). Пожалуйста, попробуйте снова через несколько минут."
    elif "Read timeout" in error_str:
        error_message = "Не удалось подключиться к серверу Unitech из-за таймаута. Проверьте интернет-соединение и попробуйте снова."
    elif "Message to be replied not found" in error_str:
        error_message = "Сообщение для ответа не найдено. Пожалуйста, попробуйте снова."
    
    logger.error("error occurred: %s\n%s", error_str, traceback.format_exc(), extra={
        'user_id': update.effective_user.id if update else 'unknown',
        'chat_id': update.effective_chat.id if update else 'unknown',
        'username': update.effective_user.username or 'unknown' if update else 'unknown'
    })
    
    if update and (update.message or update.callback_query):
        try:
            await (update.message or update.callback_query.message).reply_text(
                error_message,
                reply_markup=get_schedule_keyboard(show_menu_button=True)
            )
        except Exception as e:
            logger.error("failed to send error message: %s", str(e), extra={
                'user_id': update.effective_user.id,
                'chat_id': update.effective_chat.id,
                'username': update.effective_user.username or 'unknown'
            })
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=error_message,
                reply_markup=get_schedule_keyboard(show_menu_button=True)
            )
