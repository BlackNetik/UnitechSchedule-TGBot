# schedule.py

import requests
from icalendar import Calendar
from datetime import datetime, timedelta
import calendar

from utils import MSK, logger

class ScheduleFormatter:
    @staticmethod
    def get_pair_number(start_time):
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
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 504:
            logger.error("failed to download ICS file: %s", str(e), extra={'user_id': 'unknown', 'chat_id': 'unknown', 'username': 'unknown'})
            raise Exception("504 Server Error: Gateway Time-out")
        raise Exception(f"Failed to download ICS file: {str(e)}")
    except requests.exceptions.ReadTimeout as e:
        logger.error("failed to download ICS file: %s", str(e), extra={'user_id': 'unknown', 'chat_id': 'unknown', 'username': 'unknown'})
        raise Exception("Read timeout error: Failed to connect to server")
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