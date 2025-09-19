import requests
from icalendar import Calendar
from datetime import datetime, timezone, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes,
    ConversationHandler, CallbackQueryHandler
)
import logging
import logging.handlers
import locale
import json
import os
import re
import calendar
from get_student_id import get_schedule

# Константы для версии и даты обновления
BOT_VERSION = "1.4"
LAST_UPDATED = "19.09.2025"

# Состояния для ConversationHandler
FEEDBACK_WAITING = 1
DAY_SELECTION = 2

# Устанавливаем локаль для русского языка
try:
    locale.setlocale(locale.LC_TIME, 'Russian_Russia.1251')
except locale.Error:
    try:
        locale.setlocale(locale.LC_TIME, 'ru_RU.UTF-8')
    except locale.Error:
        locale.setlocale(locale.LC_TIME, '')

# Кастомный форматтер для логов
class CustomFormatter(logging.Formatter):
    def format(self, record):
        record.user_id = getattr(record, 'user_id', 'unknown')
        record.chat_id = getattr(record, 'chat_id', 'unknown')
        record.username = getattr(record, 'username', 'unknown')
        return super().format(record)

# Настройка логирования
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Создаем папку Logs, если она не существует
LOGS_DIR = "Logs"
if not os.path.exists(LOGS_DIR):
    os.makedirs(LOGS_DIR)

# Настраиваем ротацию логов по дням с корректным именем файла
log_base = os.path.join(LOGS_DIR, "log")
file_handler = logging.handlers.TimedRotatingFileHandler(
    log_base, when="midnight", interval=1, backupCount=30, encoding='utf-8'
)
file_handler.suffix = "%Y-%m-%d"
file_handler.setFormatter(CustomFormatter('%(asctime)s - User %(user_id)s (%(username)s) in chat %(chat_id)s: %(message)s'))
logger.addHandler(file_handler)

# Добавляем консольный вывод
stream_handler = logging.StreamHandler()
stream_handler.setFormatter(CustomFormatter('%(asctime)s - User %(user_id)s (%(username)s) in chat %(chat_id)s: %(message)s'))
logger.addHandler(stream_handler)

# Путь к файлу с API-ключом
API_KEY_FILE = 'api_key_journal_unitech.txt'

# Проверка и загрузка API-ключа
def load_api_key():
    if not os.path.exists(API_KEY_FILE):
        with open(API_KEY_FILE, 'w', encoding='utf-8') as f:
            f.write('')
        logger.error("API key file not found, created empty file: %s", API_KEY_FILE, extra={'user_id': 'system', 'chat_id': 'system', 'username': 'unknown'})
        print(f"Файл {API_KEY_FILE} создан. Пожалуйста, добавьте в него API-ключ и перезапустите программу.")
        exit(1)
    
    with open(API_KEY_FILE, 'r', encoding='utf-8') as f:
        api_key = f.read().strip()
    
    if not api_key:
        logger.error("API key is empty in file: %s", API_KEY_FILE, extra={'user_id': 'system', 'chat_id': 'system', 'username': 'unknown'})
        print(f"API-ключ в файле {API_KEY_FILE} пуст. Пожалуйста, добавьте валидный ключ и перезапустите программу.")
        exit(1)
    
    # Проверка формата API-ключа (пример: 123456789:ABCDEF...)
    if not re.match(r'^\d{8,10}:[A-Za-z0-9_-]{35}$', api_key):
        logger.error("Invalid API key format in file: %s", API_KEY_FILE, extra={'user_id': 'system', 'chat_id': 'system', 'username': 'unknown'})
        print(f"API-ключ в файле {API_KEY_FILE} имеет неверный формат. Пожалуйста, проверьте ключ и перезапустите программу.")
        exit(1)
    
    return api_key

# Загрузка API-ключа
TELEGRAM_TOKEN = load_api_key()

# Путь к JSON-файлу для хранения данных пользователей
USERS_JSON_FILE = 'users.json'

# Загрузка данных пользователей из JSON
def load_users():
    if not os.path.exists(USERS_JSON_FILE):
        with open(USERS_JSON_FILE, 'w', encoding='utf-8') as f:
            json.dump({}, f)
        logger.info("Created empty users.json", extra={'user_id': 'system', 'chat_id': 'system', 'username': 'unknown'})
    try:
        with open(USERS_JSON_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        logger.error("Failed to load users.json: %s", str(e), extra={'user_id': 'system', 'chat_id': 'system', 'username': 'unknown'})
        return {}

# Сохранение данных пользователей в JSON
def save_users(users_data):
    try:
        with open(USERS_JSON_FILE, 'w', encoding='utf-8') as f:
            json.dump(users_data, f, indent=4, ensure_ascii=False)
    except Exception as e:
        logger.error("Failed to save users.json: %s", str(e), extra={'user_id': 'system', 'chat_id': 'system', 'username': 'unknown'})

# Московский часовой пояс
MSK = timezone(timedelta(hours=3))

class ScheduleFormatter:
    @staticmethod
    def get_pair_number(start_time):
        """Определяет номер пары на основе времени начала."""
        pairs = {
            1: ("09:00", "10:30"),
            2: ("10:40", "12:10"),
            3: ("12:30", "14:00"),
            4: ("14:10", "15:40"),
            5: ("15:50", "17:20"),
            6: ("17:25", "18:55"),
            7: ("19:10", "20:30")
        }
        start_time_str = start_time.strftime('%H:%M')
        for pair_number, (start, end) in pairs.items():
            if start_time_str == start:
                return pair_number
        return None

    @staticmethod
    def format_event(event):
        try:
            start_time = event['dtstart'].astimezone(MSK)
            end_time = event['dtend'].astimezone(MSK)
            start_time_str = start_time.strftime('%H:%M')
            end_time_str = end_time.strftime('%H:%M')
            summary = event['summary']
            location = event['location']
            description = event['description']
            
            summary_lower = summary.lower()
            if 'зач' in summary_lower.split()[0]:
                emoji = '✏️'
                category = 'Зачет'
                summary = ' '.join(summary.split()[1:]) if len(summary.split()) > 1 else summary
            elif 'физ' in summary_lower or 'элективные курсы по физической культуре' in summary_lower:
                emoji = '💪'
                category = 'Физкультура'
                summary = ' '.join(summary.split()[1:]) if len(summary.split()) > 1 else summary
            elif 'лек' in summary_lower.split()[0] or 'лек.' in summary_lower.split()[0]:
                emoji = '📚'
                category = 'Лекция'
                summary = ' '.join(summary.split()[1:]) if len(summary.split()) > 1 else summary
            elif 'пр' in summary_lower.split()[0] or 'пр.' in summary_lower.split()[0] or 'прак' in summary_lower.split()[0]:
                emoji = '💻'
                category = 'Практика'
                summary = ' '.join(summary.split()[1:]) if len(summary.split()) > 1 else summary
            elif 'лаб' in summary_lower.split()[0]:
                emoji = '❗'
                category = 'Лабораторная'
                summary = ' '.join(summary.split()[1:]) if len(summary.split()) > 1 else summary
            else:
                emoji = '🔔'
                category = 'Прочее'
            
            summary = f"{summary} ({category})"
            pair_number = ScheduleFormatter.get_pair_number(start_time)
            time_prefix = f"{pair_number} пара: " if pair_number else ""
            return f" 🕘 {time_prefix}{start_time_str}-{end_time_str}\n{emoji} {summary}\nАудитория: {location}\n{description}\n"
        except Exception as e:
            logger.error("failed to format event: %s", str(e), extra={'user_id': 'unknown', 'chat_id': 'unknown', 'username': 'unknown'})
            return f"🔔 Error formatting event: {event['summary']} ({category})\n"

    @staticmethod
    def format_daily_schedule(events, date):
        events = [event for event in events if event['dtstart'].astimezone(MSK).date() == date]
        day = str(date.day)
        formatted_date = f"{day} {date.strftime('%B (%A)')}"
        if not events:
            return f"{formatted_date} занятий нет 0_о"
        sorted_events = sorted(events, key=lambda e: e['dtstart'])
        return "\n".join(ScheduleFormatter.format_event(event) for event in sorted_events)

    @staticmethod
    def format_week_schedule(events, start_date=None, end_date=None):
        if start_date and end_date:
            events = [event for event in events if start_date <= event['dtstart'].astimezone(MSK).date() <= end_date]
        if not events:
            return "Расписания на неделю нет."
        sorted_events = sorted(events, key=lambda e: e['dtstart'])
        current_date = start_date
        schedule = []
        while current_date <= end_date:
            day_events = [event for event in sorted_events if event['dtstart'].astimezone(MSK).date() == current_date]
            if current_date.weekday() >= 5 and not day_events:
                current_date += timedelta(days=1)
                continue
            day = str(current_date.day)
            formatted_date = f"{day} {current_date.strftime('%B (%A)')}"
            schedule.append(f"<----------!---------->\n📅 {formatted_date}")
            if day_events:
                schedule.append("\n".join(ScheduleFormatter.format_event(event) for event in day_events))
            elif current_date.weekday() < 5:
                schedule.append(f"{formatted_date} занятий нет 0_о")
            current_date += timedelta(days=1)
        return "\n".join(schedule)

def download_ics(id_student):
    url = f"https://es.unitech-mo.ru/api/Rasp?idStudent={id_student}&iCal=true"
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        if not response.content:
            raise Exception("Empty response from server")
        return response.content
    except requests.exceptions.RequestException as e:
        logger.error("failed to download ICS file: %s", str(e), extra={'user_id': 'unknown', 'chat_id': 'unknown', 'username': 'unknown'})
        raise Exception(f"Failed to download ICS file: {str(e)}")

def parse_ics(ics_content):
    try:
        cal = Calendar.from_ical(ics_content)
        events = []
        for component in cal.walk():
            if component.name == "VEVENT":
                event = {
                    'summary': component.get('summary', 'No summary'),
                    'dtstart': component.get('dtstart').dt if component.get('dtstart') else None,
                    'dtend': component.get('dtend').dt if component.get('dtend') else None,
                    'location': component.get('location', 'No location'),
                    'description': component.get('description', 'No description'),
                }
                if event['dtstart'] is None or event['dtend'] is None:
                    continue
                events.append(event)
        return events
    except Exception as e:
        logger.error("failed to parse ICS file: %s", str(e), extra={'user_id': 'unknown', 'chat_id': 'unknown', 'username': 'unknown'})
        raise Exception(f"Failed to parse ICS file: {str(e)}")

def get_today_schedule(events):
    today = datetime.now(MSK).date()
    return ScheduleFormatter.format_daily_schedule(events, today), today

def get_tomorrow_schedule(events):
    tomorrow = datetime.now(MSK).date() + timedelta(days=1)
    return ScheduleFormatter.format_daily_schedule(events, tomorrow), tomorrow

def get_week_schedule(events):
    today = datetime.now(MSK).date()
    days_since_monday = today.weekday()
    start_date = today - timedelta(days=days_since_monday)
    end_date = start_date + timedelta(days=6)
    return ScheduleFormatter.format_week_schedule(events, start_date, end_date), None

def get_next_week_schedule(events):
    today = datetime.now(MSK).date()
    days_until_monday = (7 - today.weekday()) % 7 or 7
    start_date = today + timedelta(days=days_until_monday)
    end_date = start_date + timedelta(days=6)
    return ScheduleFormatter.format_week_schedule(events, start_date, end_date), None

def get_day_schedule(events, day):
    today = datetime.now(MSK)
    year, month = today.year, today.month
    _, max_days = calendar.monthrange(year, month)
    if not (1 <= day <= max_days):
        return f"Ошибка: день {day} недопустим. Укажите день от 1 до {max_days} (в {today.strftime('%B')} {max_days} дней).", None
    try:
        target_date = datetime(year, month, day).date()
        return ScheduleFormatter.format_daily_schedule(events, target_date), target_date
    except ValueError:
        return f"Ошибка: день {day} недопустим для текущего месяца.", None

def get_menu_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Расп. на сегодня", callback_data="today"),
         InlineKeyboardButton("Расп. на завтра", callback_data="tomorrow")],
        [InlineKeyboardButton("Расп. на неделю", callback_data="week"),
         InlineKeyboardButton("Расп. на след. неделю", callback_data="next_week")],
        [InlineKeyboardButton("Расп. на день", callback_data="day"),
         InlineKeyboardButton("Смена группы", callback_data="change")],
        [InlineKeyboardButton("Обратная связь", callback_data="feedback")]
    ])

def get_schedule_keyboard(exclude=None, show_menu_button=True):
    today = datetime.now(MSK).date()
    buttons = []
    if exclude != "today":
        buttons.append(InlineKeyboardButton("Расп. на сегодня", callback_data="today"))
    if exclude != "tomorrow":
        buttons.append(InlineKeyboardButton("Расп. на завтра", callback_data="tomorrow"))
    if exclude != "week":
        buttons.append(InlineKeyboardButton("Расп. на неделю", callback_data="week"))
    if exclude != "next_week":
        buttons.append(InlineKeyboardButton("Расп. на след. неделю", callback_data="next_week"))
    if exclude != "day":
        buttons.append(InlineKeyboardButton("Расп. на день", callback_data="day"))
    
    keyboard = []
    row = []
    for button in buttons:
        row.append(button)
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    
    if show_menu_button:
        keyboard.append([InlineKeyboardButton("Вернуться в меню", callback_data="menu")])
    
    return InlineKeyboardMarkup(keyboard)

def get_day_selection_keyboard(page=0):
    today = datetime.now(MSK)
    year, month = today.year, today.month
    _, max_days = calendar.monthrange(year, month)
    days_per_page = 10
    start_day = page * days_per_page + 1
    end_day = min(start_day + days_per_page - 1, max_days)
    
    keyboard = []
    row = []
    for day in range(start_day, end_day + 1):
        row.append(InlineKeyboardButton(str(day), callback_data=f"day_select_{day}"))
        if len(row) == 5:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    
    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton("⬅️ Назад", callback_data=f"day_page_{page-1}"))
    if end_day < max_days:
        nav_row.append(InlineKeyboardButton("Вперед ➡️", callback_data=f"day_page_{page+1}"))
    if nav_row:
        keyboard.append(nav_row)
    
    keyboard.append([InlineKeyboardButton("Вернуться в меню", callback_data="menu")])
    return InlineKeyboardMarkup(keyboard)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_key = f"{update.effective_chat.id}"
    users_data = load_users()
    if chat_key not in users_data:
        users_data[chat_key] = {'id_student': 90893}
        save_users(users_data)
    reply_markup = get_menu_keyboard() if update.effective_chat.type == 'private' else None
    await update.message.reply_text(
        'Привет! 👋 Я бот, который поможет тебе узнать расписание занятий Технологического Университета им. А.А. Леонова с портала Unitech!\n'
        'По умолчанию показываю расписание для группы ПИ-23. Хочешь другую? Используй /change <название группы> (например, /change ПИ-23).\n'
        'Выбирай опции через кнопки (в личных сообщениях) или команды: /today, /tomorrow, /week, /next_week, /day, /info, /feedback.',
        reply_markup=reply_markup
    )
    logger.info("sent start menu", extra={
        'user_id': update.effective_user.id,
        'chat_id': update.effective_chat.id,
        'username': update.effective_user.username or 'unknown'
    })

async def info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    reply_markup = get_menu_keyboard() if update.effective_chat.type == 'private' else None
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
        f"/change — смена группы\n"
        f"/feedback — отправить обратную связь разработчику",
        reply_markup=reply_markup
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
    student_id = get_schedule(group_name)
    if not student_id:
        await update.message.reply_text(
            f"Не удалось найти группу '{group_name}' или студентов в ней. Проверьте название и попробуйте снова.",
            reply_markup=get_schedule_keyboard(show_menu_button=True)
        )
        logger.info("failed to find group or student for group: %s", group_name, extra={
            'user_id': update.effective_user.id,
            'chat_id': update.effective_chat.id,
            'username': update.effective_user.username or 'unknown'
        })
        return
    
    users_data[chat_key] = users_data.get(chat_key, {})
    users_data[chat_key]["id_student"] = student_id
    users_data[chat_key]["group_name"] = group_name
    save_users(users_data)
    await update.message.reply_text(
        f"Группа изменена на {group_name} (ID студента: {student_id})",
        reply_markup=get_schedule_keyboard(show_menu_button=True)
    )
    logger.info("changed group to %s (student ID: %s)", group_name, student_id, extra={
        'user_id': update.effective_user.id,
        'chat_id': update.effective_chat.id,
        'username': update.effective_user.username or 'unknown'
    })

async def feedback_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Пожалуйста, отправьте ваше сообщение для обратной связи."
    )
    logger.info("requested feedback message", extra={
        'user_id': update.effective_user.id,
        'chat_id': update.effective_chat.id,
        'username': update.effective_user.username or 'unknown'
    })
    return FEEDBACK_WAITING

async def feedback_receive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Check if the message is text and not empty
    if not update.message or not update.message.text or update.message.text.strip() == "":
        await update.message.reply_text(
            "Пожалуйста, отправьте текстовое сообщение (не пустое).",
            reply_markup=get_schedule_keyboard(show_menu_button=True)
        )
        logger.info("received invalid feedback: non-text or empty", extra={
            'user_id': update.effective_user.id,
            'chat_id': update.effective_chat.id,
            'username': update.effective_user.username or 'unknown'
        })
        return FEEDBACK_WAITING
    
    feedback_text = update.message.text.strip()
    username = f"@{update.effective_user.username}" if update.effective_user.username else "нет username"
    first_name = update.effective_user.first_name or "не указано"
    feedback_message = (
        f"Обратная связь от пользователя {update.effective_user.id} "
        f"({username}, Имя: {first_name}, чат {update.effective_chat.id}): {feedback_text}"
    )
    try:
        await context.bot.send_message(chat_id='-4956911463', text=feedback_message)
        await update.message.reply_text(
            "Ваше сообщение отправлено разработчику, спасибо!",
            reply_markup=get_schedule_keyboard(show_menu_button=True)
        )
        logger.info("sent feedback: %s", feedback_text, extra={
            'user_id': update.effective_user.id,
            'chat_id': update.effective_chat.id,
            'username': update.effective_user.username or 'unknown'
        })
        return ConversationHandler.END
    except Exception as e:
        await update.message.reply_text(
            f"Ошибка при отправке обратной связи: {str(e)}",
            reply_markup=get_schedule_keyboard(show_menu_button=True)
        )
        logger.error("failed to send feedback: %s", str(e), extra={
            'user_id': update.effective_user.id,
            'chat_id': update.effective_chat.id,
            'username': update.effective_user.username or 'unknown'
        })
        return ConversationHandler.END

async def feedback_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    reply_markup = get_menu_keyboard() if update.effective_chat.type == 'private' else None
    await update.message.reply_text(
        "Отправка обратной связи отменена.",
        reply_markup=reply_markup
    )
    logger.info("cancelled feedback", extra={
        'user_id': update.effective_user.id,
        'chat_id': update.effective_chat.id,
        'username': update.effective_user.username or 'unknown'
    })
    return ConversationHandler.END

async def today_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_key = f"{update.effective_chat.id}"
    users_data = load_users()
    users_data.setdefault(chat_key, {'id_student': 90893})
    try:
        id_student = users_data[chat_key]["id_student"]
        ics_content = download_ics(id_student)
        events = parse_ics(ics_content)
        schedule, _ = get_today_schedule(events)
        reply_markup = get_schedule_keyboard(exclude="today") if update.effective_chat.type == 'private' else None
        await update.message.reply_text(f"Расписание на сегодня:\n{schedule}", reply_markup=reply_markup)
        logger.info("sent today's schedule", extra={
            'user_id': update.effective_user.id,
            'chat_id': update.effective_chat.id,
            'username': update.effective_user.username or 'unknown'
        })
    except Exception as e:
        await update.message.reply_text(
            f"Ошибка при загрузке расписания: {str(e)}",
            reply_markup=get_schedule_keyboard(show_menu_button=True)
        )
        logger.error("failed to load today's schedule: %s", str(e), extra={
            'user_id': update.effective_user.id,
            'chat_id': update.effective_chat.id,
            'username': update.effective_user.username or 'unknown'
        })

async def tomorrow_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_key = f"{update.effective_chat.id}"
    users_data = load_users()
    users_data.setdefault(chat_key, {'id_student': 90893})
    try:
        id_student = users_data[chat_key]["id_student"]
        ics_content = download_ics(id_student)
        events = parse_ics(ics_content)
        schedule, _ = get_tomorrow_schedule(events)
        reply_markup = get_schedule_keyboard(exclude="tomorrow") if update.effective_chat.type == 'private' else None
        await update.message.reply_text(f"Расписание на завтра:\n{schedule}", reply_markup=reply_markup)
        logger.info("sent tomorrow's schedule", extra={
            'user_id': update.effective_user.id,
            'chat_id': update.effective_chat.id,
            'username': update.effective_user.username or 'unknown'
        })
    except Exception as e:
        await update.message.reply_text(
            f"Ошибка при загрузке расписания: {str(e)}",
            reply_markup=get_schedule_keyboard(show_menu_button=True)
        )
        logger.error("failed to load tomorrow's schedule: %s", str(e), extra={
            'user_id': update.effective_user.id,
            'chat_id': update.effective_chat.id,
            'username': update.effective_user.username or 'unknown'
        })

async def week_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_key = f"{update.effective_chat.id}"
    users_data = load_users()
    users_data.setdefault(chat_key, {'id_student': 90893})
    try:
        id_student = users_data[chat_key]["id_student"]
        ics_content = download_ics(id_student)
        events = parse_ics(ics_content)
        schedule, _ = get_week_schedule(events)
        reply_markup = get_schedule_keyboard(exclude="week") if update.effective_chat.type == 'private' else None
        await update.message.reply_text(f"Расписание на неделю:\n{schedule}", reply_markup=reply_markup)
        logger.info("sent week's schedule", extra={
            'user_id': update.effective_user.id,
            'chat_id': update.effective_chat.id,
            'username': update.effective_user.username or 'unknown'
        })
    except Exception as e:
        await update.message.reply_text(
            f"Ошибка при загрузке расписания: {str(e)}",
            reply_markup=get_schedule_keyboard(show_menu_button=True)
        )
        logger.error("failed to load week's schedule: %s", str(e), extra={
            'user_id': update.effective_user.id,
            'chat_id': update.effective_chat.id,
            'username': update.effective_user.username or 'unknown'
        })

async def next_week_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_key = f"{update.effective_chat.id}"
    users_data = load_users()
    users_data.setdefault(chat_key, {'id_student': 90893})
    try:
        id_student = users_data[chat_key]["id_student"]
        ics_content = download_ics(id_student)
        events = parse_ics(ics_content)
        schedule, _ = get_next_week_schedule(events)
        reply_markup = get_schedule_keyboard(exclude="next_week") if update.effective_chat.type == 'private' else None
        await update.message.reply_text(f"Расписание на следующую неделю:\n{schedule}", reply_markup=reply_markup)
        logger.info("sent next week's schedule", extra={
            'user_id': update.effective_user.id,
            'chat_id': update.effective_chat.id,
            'username': update.effective_user.username or 'unknown'
        })
    except Exception as e:
        await update.message.reply_text(
            f"Ошибка при загрузке расписания: {str(e)}",
            reply_markup=get_schedule_keyboard(show_menu_button=True)
        )
        logger.error("failed to load next week's schedule: %s", str(e), extra={
            'user_id': update.effective_user.id,
            'chat_id': update.effective_chat.id,
            'username': update.effective_user.username or 'unknown'
        })

async def day_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_key = f"{update.effective_chat.id}"
    users_data = load_users()
    users_data.setdefault(chat_key, {'id_student': 90893})
    
    if len(context.args) != 1:
        await update.message.reply_text(
            "Использование: /day <номер_дня> (например, /day 17)",
            reply_markup=get_schedule_keyboard(show_menu_button=True)
        )
        logger.info("invalid /day command: no or multiple arguments provided", extra={
            'user_id': update.effective_user.id,
            'chat_id': update.effective_chat.id,
            'username': update.effective_user.username or 'unknown'
        })
        return
    
    try:
        day = int(context.args[0])
    except ValueError:
        await update.message.reply_text(
            "Ошибка: номер дня должен быть числом (например, /day 17)",
            reply_markup=get_schedule_keyboard(show_menu_button=True)
        )
        logger.info("invalid /day command: non-numeric day provided", extra={
            'user_id': update.effective_user.id,
            'chat_id': update.effective_chat.id,
            'username': update.effective_user.username or 'unknown'
        })
        return
    
    try:
        id_student = users_data[chat_key]["id_student"]
        ics_content = download_ics(id_student)
        events = parse_ics(ics_content)
        schedule, target_date = get_day_schedule(events, day)
        reply_markup = get_schedule_keyboard(exclude="day") if update.effective_chat.type == 'private' else None
        await update.message.reply_text(
            f"Расписание на {day} {datetime.now(MSK).strftime('%B')}:\n{schedule}",
            reply_markup=reply_markup
        )
        logger.info("sent schedule for day %s", day, extra={
            'user_id': update.effective_user.id,
            'chat_id': update.effective_chat.id,
            'username': update.effective_user.username or 'unknown'
        })
    except Exception as e:
        await update.message.reply_text(
            f"Ошибка при загрузке расписания: {str(e)}",
            reply_markup=get_schedule_keyboard(show_menu_button=True)
        )
        logger.error("failed to load schedule for day %s: %s", day, str(e), extra={
            'user_id': update.effective_user.id,
            'chat_id': update.effective_chat.id,
            'username': update.effective_user.username or 'unknown'
        })

async def day_selection_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Выберите день для просмотра расписания:",
        reply_markup=get_day_selection_keyboard(page=0)
    )
    logger.info("started day selection", extra={
        'user_id': update.effective_user.id,
        'chat_id': update.effective_chat.id,
        'username': update.effective_user.username or 'unknown'
    })
    return DAY_SELECTION

async def day_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    username = update.effective_user.username or 'unknown'
    
    # Try to delete the previous message, but continue if it fails
    try:
        await query.message.delete()
        logger.info("deleted previous message", extra={
            'user_id': user_id,
            'chat_id': chat_id,
            'username': username
        })
    except Exception as e:
        logger.warning("failed to delete message in day_selection: %s", str(e), extra={
            'user_id': user_id,
            'chat_id': chat_id,
            'username': username
        })
    
    logger.info("processing callback: %s", query.data, extra={
        'user_id': user_id,
        'chat_id': chat_id,
        'username': username
    })
    
    # Handle menu button
    if query.data == "menu":
        try:
            await query.message.reply_text(
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
                f"/change — смена группы\n"
                f"/feedback — отправить обратную связь разработчику",
                reply_markup=get_menu_keyboard()
            )
            logger.info("returned to menu from day_selection", extra={
                'user_id': user_id,
                'chat_id': chat_id,
                'username': username
            })
            return ConversationHandler.END
        except Exception as e:
            await query.message.reply_text(
                f"Ошибка при возврате в меню: {str(e)}",
                reply_markup=get_schedule_keyboard(show_menu_button=True)
            )
            logger.error("failed to return to menu: %s", str(e), extra={
                'user_id': user_id,
                'chat_id': chat_id,
                'username': username
            })
            return ConversationHandler.END
    
    # Handle pagination
    if query.data.startswith("day_page_"):
        try:
            page = int(query.data.split("_")[-1])
            logger.info("switching to day selection page %s", page, extra={
                'user_id': user_id,
                'chat_id': chat_id,
                'username': username
            })
            await query.message.reply_text(
                "Выберите день для просмотра расписания:",
                reply_markup=get_day_selection_keyboard(page=page)
            )
            return DAY_SELECTION
        except ValueError as e:
            logger.error("invalid page number in day_page callback: %s", str(e), extra={
                'user_id': user_id,
                'chat_id': chat_id,
                'username': username
            })
            await query.message.reply_text(
                "Ошибка: неверный номер страницы.",
                reply_markup=get_schedule_keyboard(show_menu_button=True)
            )
            return ConversationHandler.END
        except Exception as e:
            logger.error("failed to switch to page: %s", str(e), extra={
                'user_id': user_id,
                'chat_id': chat_id,
                'username': username
            })
            await query.message.reply_text(
                f"Ошибка при смене страницы: {str(e)}",
                reply_markup=get_schedule_keyboard(show_menu_button=True)
            )
            return ConversationHandler.END
    
    # Handle day selection
    if query.data.startswith("day_select_"):
        try:
            day = int(query.data.split("_")[-1])
            logger.info("selected day %s", day, extra={
                'user_id': user_id,
                'chat_id': chat_id,
                'username': username
            })
            chat_key = f"{chat_id}"
            users_data = load_users()
            users_data.setdefault(chat_key, {'id_student': 90893})
            id_student = users_data[chat_key]["id_student"]
            
            try:
                ics_content = download_ics(id_student)
                events = parse_ics(ics_content)
                schedule, target_date = get_day_schedule(events, day)
            except Exception as e:
                logger.error("failed to fetch schedule for day %s: %s", day, str(e), extra={
                    'user_id': user_id,
                    'chat_id': chat_id,
                    'username': username
                })
                await query.message.reply_text(
                    f"Ошибка при загрузке расписания: {str(e)}",
                    reply_markup=get_schedule_keyboard(show_menu_button=True)
                )
                return ConversationHandler.END
            
            await query.message.reply_text(
                f"Расписание на {day} {datetime.now(MSK).strftime('%B')}:\n{schedule}",
                reply_markup=get_schedule_keyboard(exclude="day")
            )
            logger.info("sent schedule for day %s via day_selection", day, extra={
                'user_id': user_id,
                'chat_id': chat_id,
                'username': username
            })
            return ConversationHandler.END
        except ValueError as e:
            logger.error("invalid day number in day_select callback: %s", str(e), extra={
                'user_id': user_id,
                'chat_id': chat_id,
                'username': username
            })
            await query.message.reply_text(
                "Ошибка: неверный номер дня.",
                reply_markup=get_schedule_keyboard(show_menu_button=True)
            )
            return ConversationHandler.END
        except Exception as e:
            logger.error("failed to process day selection for day %s: %s", day, str(e), extra={
                'user_id': user_id,
                'chat_id': chat_id,
                'username': username
            })
            await query.message.reply_text(
                f"Ошибка при обработке выбора дня: {str(e)}",
                reply_markup=get_schedule_keyboard(show_menu_button=True)
            )
            return ConversationHandler.END
    
    # Handle unexpected callback data
    logger.warning("unexpected callback data: %s", query.data, extra={
        'user_id': user_id,
        'chat_id': chat_id,
        'username': username
    })
    await query.message.reply_text(
        "Ошибка: неизвестное действие.",
        reply_markup=get_schedule_keyboard(show_menu_button=True)
    )
    return ConversationHandler.END

async def day_selection_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    try:
        day = int(text)
    except ValueError:
        await update.message.reply_text(
            "Введите номер дня числом или используйте кнопки.",
            reply_markup=get_day_selection_keyboard(page=0)
        )
        return DAY_SELECTION
    
    chat_key = f"{update.effective_chat.id}"
    users_data = load_users()
    users_data.setdefault(chat_key, {'id_student': 90893})
    id_student = users_data[chat_key]["id_student"]

    try:
        ics_content = download_ics(id_student)
        events = parse_ics(ics_content)
        schedule, target_date = get_day_schedule(events, day)
        await update.message.reply_text(
            f"Расписание на {day} {datetime.now(MSK).strftime('%B')}:\n{schedule}",
            reply_markup=get_schedule_keyboard(exclude="day")
        )
        logger.info("sent schedule for day %s via text input", day, extra={
            'user_id': update.effective_user.id,
            'chat_id': update.effective_chat.id,
            'username': update.effective_user.username or 'unknown'
        })
        return ConversationHandler.END
    except Exception as e:
        await update.message.reply_text(
            f"Ошибка при загрузке расписания: {str(e)}",
            reply_markup=get_schedule_keyboard(show_menu_button=True)
        )
        logger.error("failed to load schedule for day %s via text input: %s", day, str(e), extra={
            'user_id': update.effective_user.id,
            'chat_id': update.effective_chat.id,
            'username': update.effective_user.username or 'unknown'
        })
        return ConversationHandler.END


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    try:
        await query.message.delete()
    except Exception as e:
        logger.error("failed to delete message in handle_callback: %s", str(e), extra={
            'user_id': update.effective_user.id,
            'chat_id': update.effective_chat.id,
            'username': update.effective_user.username or 'unknown'
        })
    
    chat_key = f"{update.effective_chat.id}"
    users_data = load_users()
    users_data.setdefault(chat_key, {'id_student': 90893})
    
    try:
        if query.data == "menu":
            await query.message.reply_text(
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
                f"/change — смена группы\n"
                f"/feedback — отправить обратную связь разработчику",
                reply_markup=get_menu_keyboard()
            )
            logger.info("returned to menu", extra={
                'user_id': update.effective_user.id,
                'chat_id': update.effective_chat.id,
                'username': update.effective_user.username or 'unknown'
            })
            return
        
        if query.data == "change":
            await query.message.reply_text(
                "Использование: /change <название группы> (например, /change ПИ-23)",
                reply_markup=get_schedule_keyboard(show_menu_button=True)
            )
            logger.info("prompted for group change", extra={
                'user_id': update.effective_user.id,
                'chat_id': update.effective_chat.id,
                'username': update.effective_user.username or 'unknown'
            })
            return
        
        if query.data == "feedback":
            await query.message.reply_text(
                "Пожалуйста, отправьте ваше сообщение для обратной связи."
            )
            logger.info("started feedback via callback", extra={
                'user_id': update.effective_user.id,
                'chat_id': update.effective_chat.id,
                'username': update.effective_user.username or 'unknown'
            })
            return FEEDBACK_WAITING
        
        if query.data == "day":
            await query.message.reply_text(
                "Выберите день для просмотра расписания:",
                reply_markup=get_day_selection_keyboard(page=0)
            )
            logger.info("started day selection via callback", extra={
                'user_id': update.effective_user.id,
                'chat_id': update.effective_chat.id,
                'username': update.effective_user.username or 'unknown'
            })
            return DAY_SELECTION
        
        id_student = users_data[chat_key]["id_student"]
        ics_content = download_ics(id_student)
        events = parse_ics(ics_content)
        
        if query.data == "today":
            schedule, _ = get_today_schedule(events)
            await query.message.reply_text(f"Расписание на сегодня:\n{schedule}", reply_markup=get_schedule_keyboard(exclude="today"))
            logger.info("sent today's schedule via callback", extra={
                'user_id': update.effective_user.id,
                'chat_id': update.effective_chat.id,
                'username': update.effective_user.username or 'unknown'
            })
        elif query.data == "tomorrow":
            schedule, _ = get_tomorrow_schedule(events)
            await query.message.reply_text(f"Расписание на завтра:\n{schedule}", reply_markup=get_schedule_keyboard(exclude="tomorrow"))
            logger.info("sent tomorrow's schedule via callback", extra={
                'user_id': update.effective_user.id,
                'chat_id': update.effective_chat.id,
                'username': update.effective_user.username or 'unknown'
            })
        elif query.data == "week":
            schedule, _ = get_week_schedule(events)
            await query.message.reply_text(f"Расписание на неделю:\n{schedule}", reply_markup=get_schedule_keyboard(exclude="week"))
            logger.info("sent week's schedule via callback", extra={
                'user_id': update.effective_user.id,
                'chat_id': update.effective_chat.id,
                'username': update.effective_user.username or 'unknown'
            })
        elif query.data == "next_week":
            schedule, _ = get_next_week_schedule(events)
            await query.message.reply_text(f"Расписание на следующую неделю:\n{schedule}", reply_markup=get_schedule_keyboard(exclude="next_week"))
            logger.info("sent next week's schedule via callback", extra={
                'user_id': update.effective_user.id,
                'chat_id': update.effective_chat.id,
                'username': update.effective_user.username or 'unknown'
            })
    except Exception as e:
        await query.message.reply_text(
            f"Ошибка при загрузке расписания: {str(e)}",
            reply_markup=get_schedule_keyboard(show_menu_button=True)
        )
        logger.error("failed to process callback %s: %s", query.data, str(e), extra={
            'user_id': update.effective_user.id,
            'chat_id': update.effective_chat.id,
            'username': update.effective_user.username or 'unknown'
        })

async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
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
            await day_command(update, context)
        except ValueError:
            await update.message.reply_text(
                "Ошибка: номер дня должен быть числом (например, Расп. на день 17)",
                reply_markup=get_schedule_keyboard(show_menu_button=True)
            )
            logger.info("invalid text day command: non-numeric day provided", extra={
                'user_id': update.effective_user.id,
                'chat_id': update.effective_chat.id,
                'username': update.effective_user.username or 'unknown'
            })
    else:
        await update.message.reply_text(
            "Пожалуйста, используйте кнопки (в личных сообщениях) или команды /today, /tomorrow, /week, /next_week, /day, /info, /feedback.",
            reply_markup=get_schedule_keyboard(show_menu_button=True)
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
    logger.error("error occurred: %s", str(context.error), extra={
        'user_id': update.effective_user.id if update else 'unknown',
        'chat_id': update.effective_chat.id if update else 'unknown',
        'username': update.effective_user.username or 'unknown' if update else 'unknown'
    })
    if update and update.message:
        await update.message.reply_text(
            f"Произошла ошибка: {str(context.error)}",
            reply_markup=get_schedule_keyboard(show_menu_button=True)
        )

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
            FEEDBACK_WAITING: [MessageHandler(filters.TEXT & ~filters.COMMAND, feedback_receive)],
        },
        fallbacks=[CommandHandler("cancel", feedback_cancel)],
        per_message=True
    ))
    app.add_handler(ConversationHandler(
        entry_points=[
            CommandHandler("day", day_selection_start),
            CallbackQueryHandler(day_selection_start, pattern="^day$")
        ],
        states={
            DAY_SELECTION: [
                CallbackQueryHandler(day_selection),  # обработка кнопок с номерами дней
                MessageHandler(filters.TEXT & ~filters.COMMAND, day_selection_text)  # обработка текстового ввода (ниже создадим)
            ],
        },
        fallbacks=[CommandHandler("cancel", feedback_cancel)],
        per_message=True
    ))
    app.add_handler(CommandHandler("today", today_command))
    app.add_handler(CommandHandler("tomorrow", tomorrow_command))
    app.add_handler(CommandHandler("week", week_command))
    app.add_handler(CommandHandler("next_week", next_week_command))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
    app.add_handler(MessageHandler(filters.COMMAND, error_handler))
    app.add_error_handler(error_handler)
    app.run_polling(timeout=20, drop_pending_updates=True)
