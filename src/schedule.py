# schedule.py

from datetime import datetime, timedelta
import calendar

from src.utils import MSK, logger
from src.study_portal import get_week_lessons, week_range_for, compute_week_type


class ScheduleFormatter:
    @staticmethod
    def categorize(lesson):
        subject_l = (lesson.get("subject") or "").lower()
        kind_l = (lesson.get("kind") or "").lower()

        if 'физ' in subject_l or 'элективные курсы по физической культуре' in subject_l:
            return '💪', 'Физкультура'
        if subject_l.startswith('зач') or 'зачет' in kind_l or 'зачёт' in kind_l:
            return '✏️', 'Зачет'
        if subject_l.startswith('экзамен') or 'экзамен' in kind_l:
            return '🎓', 'Экзамен'
        if 'лекц' in kind_l:
            return '📚', 'Лекция'
        if 'практ' in kind_l:
            return '💻', 'Практика'
        if 'лаборат' in kind_l:
            return '❗', 'Лабораторная'
        if 'консультац' in kind_l:
            return '🗣️', 'Консультация'
        return '🔔', 'Прочее'

    @staticmethod
    def format_lesson(lesson):
        try:
            emoji, category = ScheduleFormatter.categorize(lesson)
            time_prefix = f"{lesson['num']} пара: " if lesson.get('num') else ""
            room = lesson.get('room') or '?'
            building = f", {lesson['building']}" if lesson.get('building') else ""
            teacher = lesson.get('teacher') or 'не указан'
            return (
                f" 🕘 {time_prefix}{lesson['start']}-{lesson['end']}\n"
                f"{emoji} {lesson['subject']} ({category})\n"
                f"Преподаватель: {teacher}\n"
                f"Аудитория: {room}{building}\n"
            )
        except Exception as e:
            logger.error("failed to format lesson: %s", str(e), extra={'user_id': 'unknown', 'chat_id': 'unknown', 'username': 'unknown'})
            return f"🔔 Ошибка отображения занятия: {lesson.get('subject', '?')}\n"

    @staticmethod
    def format_daily_schedule(days, date):
        lessons = days.get(date, [])
        day = str(date.day)
        formatted_date = f"{day} {date.strftime('%B (%A)')}"
        if not lessons:
            return f"{formatted_date} занятий нет 0_о"
        return "\n".join(ScheduleFormatter.format_lesson(lesson) for lesson in lessons)

    @staticmethod
    def format_week_schedule(days, start_date, end_date):
        schedule = []
        current_date = start_date
        any_lessons = False
        while current_date <= end_date:
            lessons = days.get(current_date, [])
            if lessons:
                any_lessons = True
            if current_date.weekday() >= 5 and not lessons:
                current_date += timedelta(days=1)
                continue
            day = str(current_date.day)
            formatted_date = f"{day} {current_date.strftime('%B (%A)')}"
            schedule.append(f"<----------!---------->\n📅 {formatted_date}")
            if lessons:
                schedule.append("\n".join(ScheduleFormatter.format_lesson(lesson) for lesson in lessons))
            else:
                schedule.append(f"{formatted_date} занятий нет 0_о")
            current_date += timedelta(days=1)
        if not any_lessons:
            return "Расписания на неделю нет."
        return "\n".join(schedule)


async def get_today_schedule(group_id):
    today = datetime.now(MSK).date()
    monday, _ = week_range_for(today)
    days = await get_week_lessons(group_id, monday)
    return ScheduleFormatter.format_daily_schedule(days, today), today


async def get_tomorrow_schedule(group_id):
    tomorrow = datetime.now(MSK).date() + timedelta(days=1)
    monday, _ = week_range_for(tomorrow)
    days = await get_week_lessons(group_id, monday)
    return ScheduleFormatter.format_daily_schedule(days, tomorrow), tomorrow


async def get_week_schedule(group_id):
    today = datetime.now(MSK).date()
    monday, sunday = week_range_for(today)
    days = await get_week_lessons(group_id, monday)
    week_type = compute_week_type(monday).capitalize()
    schedule = ScheduleFormatter.format_week_schedule(days, monday, sunday)
    return f"{week_type} неделя\n{schedule}", None


async def get_next_week_schedule(group_id):
    today = datetime.now(MSK).date()
    monday, sunday = week_range_for(today)
    next_monday, next_sunday = monday + timedelta(days=7), sunday + timedelta(days=7)
    days = await get_week_lessons(group_id, next_monday)
    week_type = compute_week_type(next_monday).capitalize()
    schedule = ScheduleFormatter.format_week_schedule(days, next_monday, next_sunday)
    return f"{week_type} неделя\n{schedule}", None


async def get_day_schedule(group_id, day):
    today = datetime.now(MSK)
    year, month = today.year, today.month
    _, max_days = calendar.monthrange(year, month)
    if not (1 <= day <= max_days):
        return f"Ошибка: день {day} недопустим. Укажите день от 1 до {max_days} (в {today.strftime('%B')} {max_days} дней).", None
    try:
        target_date = datetime(year, month, day).date()
    except ValueError:
        return f"Ошибка: день {day} недопустим для текущего месяца.", None

    monday, _ = week_range_for(target_date)
    days = await get_week_lessons(group_id, monday)
    return ScheduleFormatter.format_daily_schedule(days, target_date), target_date
