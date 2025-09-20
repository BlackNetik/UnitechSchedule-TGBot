# keyboards.py

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from datetime import datetime
import calendar
from utils import MSK

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