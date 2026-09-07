# handlers.py

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler
import traceback

from config import BOT_VERSION, LAST_UPDATED, FEEDBACK_WAITING, DAY_SELECTION, DEFAULT_GROUP_ID, DEFAULT_GROUP_NAME
from src.utils import load_users, save_users, MSK, logger
from src.keyboards import get_menu_keyboard, get_schedule_keyboard, get_day_selection_keyboard
from src.schedule import get_today_schedule, get_tomorrow_schedule, get_week_schedule, get_next_week_schedule, get_day_schedule
from src.study_portal import resolve_group_id

from config import CHANGE_GROUP_WAITING, DEVELOPER_CHAT_ID, DEVELOPER_USERNAME


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_key = f"{update.effective_chat.id}"
    users_data = load_users()
    if chat_key not in users_data:
        users_data[chat_key] = {'group_id': DEFAULT_GROUP_ID, 'group_name': DEFAULT_GROUP_NAME}
        save_users(users_data)
    await update.message.reply_text(
        'Привет! 👋 Я бот, который поможет тебе узнать расписание занятий Технологического Университета им. А.А. Леонова с портала МИИГАиК!\n'
        f'По умолчанию показываю расписание для группы {DEFAULT_GROUP_NAME}. Хочешь другую? Используй /change <название группы> (например, /change {DEFAULT_GROUP_NAME}).\n'
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
        f"Этот бот предоставляет расписание занятий на основе данных с портала МИИГАиК (study.miigaik.ru).\n"
        f"Бот был написан сотрудником МОРС с помощью AI\n"
        f"Расписание доступно для всех групп, используйте /change <название группы> для смены.\n"
        f"Дата создания: 01.09.2025. Текущая версия: {BOT_VERSION} от {LAST_UPDATED}\n"
        f"\nИспользуйте команды:\n"
        f"/today — расписание на сегодня\n"
        f"/tomorrow — расписание на завтра\n"
        f"/week — расписание на неделю\n"
        f"/next_week — расписание на следующую неделю\n"
        f"/day <номер_дня> — расписание на указанный день текущего месяца\n"
        f"/change — смена группы\n"
        f"/feedback — отправить обратную связь разработчику",
        reply_markup=get_menu_keyboard()
    )
    logger.info("sent info", extra={
        'user_id': update.effective_user.id,
        'chat_id': update.effective_chat.id,
        'username': update.effective_user.username or 'unknown'
    })


def _error_message(e: Exception) -> str:
    error_str = str(e)
    if "504" in error_str:
        return "Портал МИИГАиК временно недоступен (ошибка 504). Пожалуйста, попробуйте снова через несколько минут."
    if "Read timeout" in error_str:
        return "Не удалось подключиться к порталу МИИГАиК из-за таймаута. Проверьте интернет-соединение и попробуйте снова."
    return "Произошла ошибка при загрузке расписания. Пожалуйста, попробуйте еще раз."


async def get_user_group(chat_key):
    """
    Возвращает (group_id, group_name, user_data) для чата.

    Заодно самостоятельно "мигрирует" записи, оставшиеся от старой версии
    бота (там, где группа определялась через id_student на es.unitech-mo.ru):
    если group_id ещё не сохранён, группа переопределяется на новом портале
    по названию (group_name, если оно было сохранено, иначе группа по
    умолчанию), и результат сохраняется — так что лишний запрос к порталу
    происходит максимум один раз на пользователя.
    """
    users_data = load_users()
    user_data = users_data.get(chat_key, {})

    if 'group_id' in user_data and 'group_name' in user_data:
        return user_data['group_id'], user_data['group_name'], user_data

    group_name = user_data.get('group_name') or DEFAULT_GROUP_NAME
    group = await resolve_group_id(group_name)
    if group is None:
        group_id, group_name = DEFAULT_GROUP_ID, DEFAULT_GROUP_NAME
    else:
        group_id, group_name = group['id'], group['name']

    user_data = {'group_id': group_id, 'group_name': group_name}
    users_data[chat_key] = user_data
    save_users(users_data)
    return group_id, group_name, user_data


async def change_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 1:
        await update.message.reply_text(
            f"Использование: /change <название группы> (например, /change {DEFAULT_GROUP_NAME})"
        )
        logger.info("invalid /change command: no group name provided", extra={
            'user_id': update.effective_user.id,
            'chat_id': update.effective_chat.id,
            'username': update.effective_user.username or 'unknown'
        })
        return

    await _apply_group_change(update, context, ' '.join(context.args))


async def _apply_group_change(update: Update, context: ContextTypes.DEFAULT_TYPE, group_name: str):
    chat_key = f"{update.effective_chat.id}"
    users_data = load_users()

    try:
        group = await resolve_group_id(group_name)
        if not group:
            await update.message.reply_text(
                f"Не удалось найти группу '{group_name}'. Проверьте название и попробуйте снова.",
                reply_markup=get_menu_keyboard()
            )
            logger.info("failed to find group: %s", group_name, extra={
                'user_id': update.effective_user.id,
                'chat_id': update.effective_chat.id,
                'username': update.effective_user.username or 'unknown'
            })
            return
    except Exception as e:
        logger.info("failed to look up group %s: %s", group_name, str(e), extra={
            'user_id': update.effective_user.id,
            'chat_id': update.effective_chat.id,
            'username': update.effective_user.username or 'unknown'
        })
        await update.message.reply_text(
            _error_message(e),
            reply_markup=get_menu_keyboard()
        )
        return

    users_data[chat_key] = {'group_id': group['id'], 'group_name': group['name']}
    save_users(users_data)
    await update.message.reply_text(
        f"Группа изменена на {group['name']}",
        reply_markup=get_menu_keyboard()
    )
    logger.info("changed group to %s (id: %s)", group['name'], group['id'], extra={
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


async def today_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_key = f"{update.effective_chat.id}"

    try:
        group_id, _, _ = await get_user_group(chat_key)
        schedule, _ = await get_today_schedule(group_id)

        await update.message.reply_text(
            f"Расписание на сегодня:\n{schedule}",
            reply_markup=get_schedule_keyboard(exclude="today")
        )
        logger.info("sent today's schedule", extra={
            'user_id': update.effective_user.id,
            'chat_id': update.effective_chat.id,
            'username': update.effective_user.username or 'unknown'
        })
    except Exception as e:
        await update.message.reply_text(
            _error_message(e),
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
        group_id, _, _ = await get_user_group(chat_key)
        schedule, _ = await get_tomorrow_schedule(group_id)

        await update.message.reply_text(
            f"Расписание на завтра:\n{schedule}",
            reply_markup=get_schedule_keyboard(exclude="tomorrow")
        )
        logger.info("sent tomorrow's schedule", extra={
            'user_id': update.effective_user.id,
            'chat_id': update.effective_chat.id,
            'username': update.effective_user.username or 'unknown'
        })
    except Exception as e:
        await update.message.reply_text(
            _error_message(e),
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
        group_id, _, _ = await get_user_group(chat_key)
        schedule, _ = await get_week_schedule(group_id)
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
        await update.message.reply_text(
            _error_message(e),
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
        group_id, _, _ = await get_user_group(chat_key)
        schedule, _ = await get_next_week_schedule(group_id)
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
        await update.message.reply_text(
            _error_message(e),
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
        group_id, _, _ = await get_user_group(chat_key)
        schedule, _ = await get_day_schedule(group_id, day)
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
        error_message = _error_message(e)
        try:
            await (update.message or update.callback_query.message).reply_text(
                error_message,
                reply_markup=get_schedule_keyboard(show_menu_button=True)
            )
        except Exception:
            await context.bot.send_message(
                chat_id=chat_id,
                text=error_message,
                reply_markup=get_schedule_keyboard(show_menu_button=True)
            )
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

    chat_key = f"{update.effective_chat.id}"

    try:
        group_id, _, _ = await get_user_group(chat_key)

        if query.data == "today":
            schedule, _ = await get_today_schedule(group_id)
            await send_message(
                query, context,
                f"Расписание на сегодня:\n{schedule}",
                reply_markup=get_schedule_keyboard(exclude="today")
            )
            logger.info("sent today's schedule via callback", extra={
                'user_id': update.effective_user.id,
                'chat_id': update.effective_chat.id,
                'username': update.effective_user.username or 'unknown'
            })
        elif query.data == "tomorrow":
            schedule, _ = await get_tomorrow_schedule(group_id)
            await send_message(
                query, context,
                f"Расписание на завтра:\n{schedule}",
                reply_markup=get_schedule_keyboard(exclude="tomorrow")
            )
            logger.info("sent tomorrow's schedule via callback", extra={
                'user_id': update.effective_user.id,
                'chat_id': update.effective_chat.id,
                'username': update.effective_user.username or 'unknown'
            })
        elif query.data == "week":
            schedule, _ = await get_week_schedule(group_id)
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
            schedule, _ = await get_next_week_schedule(group_id)
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
    except Exception as e:
        await send_message(
            query, context,
            _error_message(e),
            reply_markup=get_schedule_keyboard(show_menu_button=True)
        )
        logger.error("failed to process callback %s: %s", query.data, str(e), extra={
            'user_id': update.effective_user.id,
            'chat_id': update.effective_chat.id,
            'username': update.effective_user.username or 'unknown'
        })


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
        f"Введите название группы (например, {DEFAULT_GROUP_NAME}):"
    )
    logger.info("started group change", extra={
        'user_id': update.effective_user.id,
        'chat_id': update.effective_chat.id,
        'username': update.effective_user.username or 'unknown'
    })
    return CHANGE_GROUP_WAITING


async def change_receive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает ввод названия группы после /change или кнопки "Изменить расп."."""
    group_name = update.message.text.strip()
    await _apply_group_change(update, context, group_name)
    return ConversationHandler.END


async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if update.effective_chat.type in ['group', 'supergroup']:
        # Берём username из кэша (заполняется в post_init при старте).
        # Никаких сетевых запросов get_me() здесь — иначе таймаут на каждом чужом сообщении
        # летит в error_handler, который пытается ответить в чат → бот спамит ошибками.
        bot_username = context.bot_data.get('username') or context.bot.username or ''
        mention = '@' + bot_username
        # Безопасная проверка reply — from_user может быть None (анонимный админ, пост из канала)
        reply_msg = update.message.reply_to_message
        reply_is_bot = (
            reply_msg is not None
            and reply_msg.from_user is not None
            and reply_msg.from_user.id == context.bot.id
        )
        if not (mention in text or reply_is_bot):
            return
        text = text.replace(mention, '').strip()

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
    error_str = str(context.error) if context.error else "None"

    logger.error("error occurred: %s\n%s", error_str, traceback.format_exc(), extra={
        'user_id': update.effective_user.id if update else 'unknown',
        'chat_id': update.effective_chat.id if update else 'unknown',
        'username': update.effective_user.username or 'unknown' if update else 'unknown'
    })

    # Сетевые таймауты (Timed out, TimedOut) — это проблема соединения, а не действия пользователя.
    # Не пытаемся отправить сообщение об ошибке: сеть и так недоступна, и бот только заспамит чат.
    if "Timed out" in error_str or "TimedOut" in error_str:
        return

    if "Message to be replied not found" in error_str:
        error_message = "Сообщение для ответа не найдено. Пожалуйста, попробуйте снова."
    elif "504" in error_str or "Read timeout" in error_str:
        error_message = _error_message(context.error)
    else:
        error_message = "Произошла неизвестная ошибка. Пожалуйста, попробуйте еще раз."

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
