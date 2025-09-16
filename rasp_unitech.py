import requests
from icalendar import Calendar
from datetime import datetime, timezone, timedelta
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes,
    ConversationHandler
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
BOT_VERSION = "1.31"
LAST_UPDATED = "16.09.2025"

# Состояния для ConversationHandler
FEEDBACK_WAITING = 1

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
        current_date = None
        schedule = []
        for event in sorted_events:
            event_date = event['dtstart'].astimezone(MSK).date()
            if event_date != current_date:
                current_date = event_date
                day = str(current_date.day)
                formatted_date = f"{day} {current_date.strftime('%B (%A)')}"
                schedule.append(f"<----------!---------->\n📅 {formatted_date}")
            schedule.append(ScheduleFormatter.format_event(event))
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
    return ScheduleFormatter.format_daily_schedule(events, today)

def get_tomorrow_schedule(events):
    tomorrow = datetime.now(MSK).date() + timedelta(days=1)
    return ScheduleFormatter.format_daily_schedule(events, tomorrow)

def get_week_schedule(events):
    today = datetime.now(MSK).date()
    days_since_monday = today.weekday()  # 0=понедельник, 6=воскресенье
    start_date = today - timedelta(days=days_since_monday)  # Понедельник текущей недели
    end_date = start_date + timedelta(days=6)  # Воскресенье текущей недели
    return ScheduleFormatter.format_week_schedule(events, start_date, end_date)

def get_next_week_schedule(events):
    today = datetime.now(MSK).date()
    days_until_monday = (7 - today.weekday()) % 7 or 7
    start_date = today + timedelta(days=days_until_monday)
    end_date = start_date + timedelta(days=6)
    return ScheduleFormatter.format_week_schedule(events, start_date, end_date)

def get_day_schedule(events, day):
    today = datetime.now(MSK)
    year, month = today.year, today.month
    _, max_days = calendar.monthrange(year, month)
    if not (1 <= day <= max_days):
        return f"Ошибка: день {day} недопустим. Укажите день от 1 до {max_days}."
    try:
        target_date = datetime(year, month, day).date()
        return ScheduleFormatter.format_daily_schedule(events, target_date)
    except ValueError:
        return f"Ошибка: день {day} недопустим для текущего месяца."

def start_keyboard():
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton("Расп. на сегодня")],
            [KeyboardButton("Расп. на завтра")],
            [KeyboardButton("Расп. на неделю")],
            [KeyboardButton("Расп. на след. неделю")],
            [KeyboardButton("Расп. на день")],
        ],
        resize_keyboard=True
    )

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_chat_key = f"{update.effective_user.id}_{update.effective_chat.id}"
    users_data = load_users()
    if user_chat_key not in users_data:
        users_data[user_chat_key] = {'id_student': 90893}
        save_users(users_data)
    reply_markup = start_keyboard() if update.effective_chat.type == 'private' else None
    await update.message.reply_text(
        'Привет! 👋 Я бот, который поможет тебе узнать расписание занятий МТУСИ с портала Unitech!\n'
        'По умолчанию показываю расписание для группы ПИ-23. Хочешь другую? Используй /change <название группы> (например, /change ПИ-23).\n'
        'Выбирай опции через кнопки (в личных сообщениях) или команды: /today, /tomorrow, /week, /next_week, /day, /info, /report, /change, /change_info, /feedback.',
        reply_markup=reply_markup
    )
    logger.info("sent start menu", extra={
        'user_id': update.effective_user.id,
        'chat_id': update.effective_chat.id,
        'username': update.effective_user.username or 'unknown'
    })

async def change_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_chat_key = f"{update.effective_user.id}_{update.effective_chat.id}"
    users_data = load_users()
    if len(context.args) < 1:
        await update.message.reply_text("Использование: /change <название группы> (например, /change ПИ-23)")
        logger.info("invalid /change command: no group name provided", extra={
            'user_id': update.effective_user.id,
            'chat_id': update.effective_chat.id,
            'username': update.effective_user.username or 'unknown'
        })
        return
    
    group_name = ' '.join(context.args)
    student_id = get_schedule(group_name)
    if not student_id:
        await update.message.reply_text(f"Не удалось найти группу '{group_name}' или студентов в ней. Проверьте название и попробуйте снова.")
        logger.info("failed to find group or student for group: %s", group_name, extra={
            'user_id': update.effective_user.id,
            'chat_id': update.effective_chat.id,
            'username': update.effective_user.username or 'unknown'
        })
        return
    
    users_data[user_chat_key] = users_data.get(user_chat_key, {})
    users_data[user_chat_key]["id_student"] = student_id
    users_data[user_chat_key]["group_name"] = group_name
    save_users(users_data)
    await update.message.reply_text(f"Группа изменена на {group_name} (ID студента: {student_id})")
    logger.info("changed group to %s (student ID: %s)", group_name, student_id, extra={
        'user_id': update.effective_user.id,
        'chat_id': update.effective_chat.id,
        'username': update.effective_user.username or 'unknown'
    })

async def change_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📍 Как узнать название группы для команды /change:\n\n"
        "🔹 Зайдите на портал: https://es.unitech-mo.ru/\n"
        "🔹 Перейдите в раздел «Справочник» → «Группы».\n"
        "🔹 Найдите свою группу в списке (например, ПИ-23).\n"
        "🔹 Используйте команду: /change ПИ-23\n\n"
        "Готово! Теперь вы можете смотреть расписание своей группы. 🎉"
    )
    logger.info("sent change info", extra={
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
        f"/change — смена группы\n"
        f"/change_info — как узнать название группы\n"
        f"/report — отправить жалобу или предложение\n"
        f"/feedback — отправить обратную связь разработчику"
    )
    logger.info("sent info", extra={
        'user_id': update.effective_user.id,
        'chat_id': update.effective_chat.id,
        'username': update.effective_user.username or 'unknown'
    })

async def report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Пожалуйста, отправьте вашу локацию 🤗",
        reply_markup=ReplyKeyboardMarkup(
            [[KeyboardButton("Отправить локацию", request_location=True)]],
            resize_keyboard=True,
            one_time_keyboard=True
        )
    )
    logger.info("requested location", extra={
        'user_id': update.effective_user.id,
        'chat_id': update.effective_chat.id,
        'username': update.effective_user.username or 'unknown'
    })

async def feedback_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Пожалуйста, отправьте ваше сообщение для обратной связи.")
    logger.info("requested feedback message", extra={
        'user_id': update.effective_user.id,
        'chat_id': update.effective_chat.id,
        'username': update.effective_user.username or 'unknown'
    })
    return FEEDBACK_WAITING

async def feedback_receive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.text:
        await update.message.reply_text("Пожалуйста, отправьте текстовое сообщение.")
        logger.info("received non-text feedback", extra={
            'user_id': update.effective_user.id,
            'chat_id': update.effective_chat.id,
            'username': update.effective_user.username or 'unknown'
        })
        return FEEDBACK_WAITING
    
    feedback_text = update.message.text
    username = f"@{update.effective_user.username}" if update.effective_user.username else "нет username"
    first_name = update.effective_user.first_name or "не указано"
    feedback_message = (
        f"Обратная связь от пользователя {update.effective_user.id} "
        f"({username}, Имя: {first_name}, чат {update.effective_chat.id}): {feedback_text}"
    )
    try:
        await context.bot.send_message(chat_id='-4956911463', text=feedback_message)
        await update.message.reply_text("Ваше сообщение отправлено разработчику, спасибо!")
        logger.info("sent feedback: %s", feedback_text, extra={
            'user_id': update.effective_user.id,
            'chat_id': update.effective_chat.id,
            'username': update.effective_user.username or 'unknown'
        })
        return ConversationHandler.END
    except Exception as e:
        await update.message.reply_text(f"Ошибка при отправке обратной связи: {str(e)}")
        logger.error("failed to send feedback: %s", str(e), extra={
            'user_id': update.effective_user.id,
            'chat_id': update.effective_chat.id,
            'username': update.effective_user.username or 'unknown'
        })
        return ConversationHandler.END

async def feedback_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    reply_markup = start_keyboard() if update.effective_chat.type == 'private' else None
    await update.message.reply_text("Отправка обратной связи отменена.", reply_markup=reply_markup)
    logger.info("cancelled feedback", extra={
        'user_id': update.effective_user.id,
        'chat_id': update.effective_chat.id,
        'username': update.effective_user.username or 'unknown'
    })
    return ConversationHandler.END

async def location_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    location = update.message.location
    reply_markup = start_keyboard() if update.effective_chat.type == 'private' else None
    if location:
        latitude = location.latitude
        longitude = location.longitude
        await update.message.reply_text(
            f"Ваша геолокация получена: широта {latitude}, долгота {longitude}.\nВ течении пяти минут к вам приедет СПЕЦНАЗ и проведёт воспитательную беседу! Просьба не сопротивляться и открыть дверь при первом стуке!\nТакже мы прямо сейчас вам устанавливаем национальный мессенджер MAX\n\n\nMAX — новая цифровая платформа, которая объединяет в себе сервисы для решения повседневных задач и мессенджер для комфортного общения. Это быстрое и легкое приложение, где можно переписываться, звонить, отправлять стикеры, голосовые сообщения и пользоваться разными полезными сервисами. \nMAX работает стабильно даже при слабом интернет-соединении, чтобы вы всегда оставались на связи.",
            reply_markup=reply_markup
        )
        logger.info("received location (lat: %s, lon: %s)", latitude, longitude, extra={
            'user_id': update.effective_user.id,
            'chat_id': update.effective_chat.id,
            'username': update.effective_user.username or 'unknown'
        })
    else:
        await update.message.reply_text(
            "Не удалось получить локацию. Пожалуйста, попробуйте снова.",
            reply_markup=reply_markup
        )
        logger.info("failed to receive location", extra={
            'user_id': update.effective_user.id,
            'chat_id': update.effective_chat.id,
            'username': update.effective_user.username or 'unknown'
        })

async def today_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_chat_key = f"{update.effective_user.id}_{update.effective_chat.id}"
    users_data = load_users()
    users_data.setdefault(user_chat_key, {'id_student': 90893})
    try:
        id_student = users_data[user_chat_key]["id_student"]
        ics_content = download_ics(id_student)
        events = parse_ics(ics_content)
        schedule = get_today_schedule(events)
        await update.message.reply_text(f"Расписание на сегодня:\n{schedule}")
        logger.info("sent today's schedule", extra={
            'user_id': update.effective_user.id,
            'chat_id': update.effective_chat.id,
            'username': update.effective_user.username or 'unknown'
        })
    except Exception as e:
        await update.message.reply_text(f"Ошибка при загрузке расписания: {str(e)}")
        logger.error("failed to load today's schedule: %s", str(e), extra={
            'user_id': update.effective_user.id,
            'chat_id': update.effective_chat.id,
            'username': update.effective_user.username or 'unknown'
        })

async def tomorrow_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_chat_key = f"{update.effective_user.id}_{update.effective_chat.id}"
    users_data = load_users()
    users_data.setdefault(user_chat_key, {'id_student': 90893})
    try:
        id_student = users_data[user_chat_key]["id_student"]
        ics_content = download_ics(id_student)
        events = parse_ics(ics_content)
        schedule = get_tomorrow_schedule(events)
        await update.message.reply_text(f"Расписание на завтра:\n{schedule}")
        logger.info("sent tomorrow's schedule", extra={
            'user_id': update.effective_user.id,
            'chat_id': update.effective_chat.id,
            'username': update.effective_user.username or 'unknown'
        })
    except Exception as e:
        await update.message.reply_text(f"Ошибка при загрузке расписания: {str(e)}")
        logger.error("failed to load tomorrow's schedule: %s", str(e), extra={
            'user_id': update.effective_user.id,
            'chat_id': update.effective_chat.id,
            'username': update.effective_user.username or 'unknown'
        })

async def week_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_chat_key = f"{update.effective_user.id}_{update.effective_chat.id}"
    users_data = load_users()
    users_data.setdefault(user_chat_key, {'id_student': 90893})
    try:
        id_student = users_data[user_chat_key]["id_student"]
        ics_content = download_ics(id_student)
        events = parse_ics(ics_content)
        schedule = get_week_schedule(events)
        await update.message.reply_text(f"Расписание на неделю:\n{schedule}")
        logger.info("sent week's schedule", extra={
            'user_id': update.effective_user.id,
            'chat_id': update.effective_chat.id,
            'username': update.effective_user.username or 'unknown'
        })
    except Exception as e:
        await update.message.reply_text(f"Ошибка при загрузке расписания: {str(e)}")
        logger.error("failed to load week's schedule: %s", str(e), extra={
            'user_id': update.effective_user.id,
            'chat_id': update.effective_chat.id,
            'username': update.effective_user.username or 'unknown'
        })

async def next_week_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_chat_key = f"{update.effective_user.id}_{update.effective_chat.id}"
    users_data = load_users()
    users_data.setdefault(user_chat_key, {'id_student': 90893})
    try:
        id_student = users_data[user_chat_key]["id_student"]
        ics_content = download_ics(id_student)
        events = parse_ics(ics_content)
        schedule = get_next_week_schedule(events)
        await update.message.reply_text(f"Расписание на следующую неделю:\n{schedule}")
        logger.info("sent next week's schedule", extra={
            'user_id': update.effective_user.id,
            'chat_id': update.effective_chat.id,
            'username': update.effective_user.username or 'unknown'
        })
    except Exception as e:
        await update.message.reply_text(f"Ошибка при загрузке расписания: {str(e)}")
        logger.error("failed to load next week's schedule: %s", str(e), extra={
            'user_id': update.effective_user.id,
            'chat_id': update.effective_chat.id,
            'username': update.effective_user.username or 'unknown'
        })

async def day_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_chat_key = f"{update.effective_user.id}_{update.effective_chat.id}"
    users_data = load_users()
    users_data.setdefault(user_chat_key, {'id_student': 90893})
    
    if len(context.args) != 1:
        await update.message.reply_text("Использование: /day <номер_дня> (например, /day 17)")
        logger.info("invalid /day command: no or multiple arguments provided", extra={
            'user_id': update.effective_user.id,
            'chat_id': update.effective_chat.id,
            'username': update.effective_user.username or 'unknown'
        })
        return
    
    try:
        day = int(context.args[0])
    except ValueError:
        await update.message.reply_text("Ошибка: номер дня должен быть числом (например, /day 17)")
        logger.info("invalid /day command: non-numeric day provided", extra={
            'user_id': update.effective_user.id,
            'chat_id': update.effective_chat.id,
            'username': update.effective_user.username or 'unknown'
        })
        return
    
    try:
        id_student = users_data[user_chat_key]["id_student"]
        ics_content = download_ics(id_student)
        events = parse_ics(ics_content)
        schedule = get_day_schedule(events, day)
        await update.message.reply_text(f"Расписание на {day} {datetime.now(MSK).strftime('%B')}:\n{schedule}")
        logger.info("sent schedule for day %s", day, extra={
            'user_id': update.effective_user.id,
            'chat_id': update.effective_chat.id,
            'username': update.effective_user.username or 'unknown'
        })
    except Exception as e:
        await update.message.reply_text(f"Ошибка при загрузке расписания: {str(e)}")
        logger.error("failed to load schedule for day %s: %s", day, str(e), extra={
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
            await update.message.reply_text("Ошибка: номер дня должен быть числом (например, Расп. на день 17)")
            logger.info("invalid text day command: non-numeric day provided", extra={
                'user_id': update.effective_user.id,
                'chat_id': update.effective_chat.id,
                'username': update.effective_user.username or 'unknown'
            })
    else:
        await update.message.reply_text("Пожалуйста, используйте кнопки (в личных сообщениях) или команды /today, /tomorrow, /week, /next_week, /day, /info, /report, /change, /change_info, /feedback.")
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
        await update.message.reply_text(f"Произошла ошибка: {str(context.error)}")

if __name__ == '__main__':
    logger.info("bot started", extra={'user_id': 'system', 'chat_id': 'system', 'username': 'unknown'})
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("change", change_command))
    app.add_handler(CommandHandler("change_info", change_info))
    app.add_handler(CommandHandler("info", info))
    app.add_handler(CommandHandler("report", report))
    app.add_handler(ConversationHandler(
        entry_points=[CommandHandler("feedback", feedback_start)],
        states={
            FEEDBACK_WAITING: [MessageHandler(filters.TEXT & ~filters.COMMAND, feedback_receive)],
        },
        fallbacks=[CommandHandler("cancel", feedback_cancel)]
    ))
    app.add_handler(CommandHandler("today", today_command))
    app.add_handler(CommandHandler("tomorrow", tomorrow_command))
    app.add_handler(CommandHandler("week", week_command))
    app.add_handler(CommandHandler("next_week", next_week_command))
    app.add_handler(CommandHandler("day", day_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
    app.add_handler(MessageHandler(filters.LOCATION, location_handler))
    app.add_error_handler(error_handler)
    app.run_polling(timeout=20, drop_pending_updates=True)
