# study_portal.py
#
# Клиент для нового портала расписания МИИГАиК (study.miigaik.ru), который
# заменил старый es.unitech-mo.ru. Портал не отдаёт ICS/JSON с расписанием —
# страница на Django+HTMX+Alpine.js, но список групп и сами занятия
# рендерятся на сервере и присутствуют в обычном HTML-ответе (Alpine только
# раскрашивает то, что уже пришло с сервера), поэтому обычный GET-запрос
# без исполнения JS отдаёт всё, что нужно.

import html as html_module
import json
import re
from datetime import date, datetime, timedelta

import httpx
from bs4 import BeautifulSoup

from config import ORG_ID, PORTAL_BASE_URL
from src.utils import logger

# Понедельник верхней недели, от которой считается чередование
# "верхняя"/"нижняя" неделя (см. baseUpperWeekDate в JS портала).
_BASE_UPPER_WEEK_MONDAY = date(2025, 9, 1)

_GROUPS_SCRIPT_RE = re.compile(
    r'<script[^>]*id=["\']groups-data["\'][^>]*>(.*?)</script>',
    re.DOTALL | re.IGNORECASE,
)


def monday_of(d: date) -> date:
    """Понедельник недели, в которой лежит дата d."""
    return d - timedelta(days=d.weekday())


def week_range_for(d: date) -> tuple[date, date]:
    """Границы недели (пн, вс), в которую попадает дата d."""
    start = monday_of(d)
    return start, start + timedelta(days=6)


def compute_week_type(monday_date: date) -> str:
    """"Верхняя" или "нижняя" неделя — как считает сам портал."""
    base_monday = monday_of(_BASE_UPPER_WEEK_MONDAY)
    diff_weeks = (monday_date - base_monday).days // 7
    return "верхняя" if diff_weeks % 2 == 0 else "нижняя"


async def fetch_page(group_id: int, date_start: date = None, date_end: date = None,
                      org_id: int = ORG_ID) -> str:
    """Скачивает HTML страницы расписания группы с портала."""
    params = {"orgId": org_id}
    if group_id is not None:
        params["groupId"] = group_id
    if date_start is not None:
        params["dateStart"] = date_start.isoformat()
    if date_end is not None:
        params["dateEnd"] = date_end.isoformat()

    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            response = await client.get(PORTAL_BASE_URL + "/", params=params)
            response.raise_for_status()
            if not response.text:
                raise Exception("Empty response from server")
            return response.text
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 504:
            logger.error("failed to download schedule page: %s", str(e),
                         extra={'user_id': 'unknown', 'chat_id': 'unknown', 'username': 'unknown'})
            raise Exception("504 Server Error: Gateway Time-out")
        raise Exception(f"Failed to download schedule page: {str(e)}")
    except httpx.TimeoutException as e:
        logger.error("failed to download schedule page (timeout): %s", str(e),
                     extra={'user_id': 'unknown', 'chat_id': 'unknown', 'username': 'unknown'})
        raise Exception("Read timeout error: Failed to connect to server")
    except httpx.RequestError as e:
        logger.error("failed to download schedule page: %s", str(e),
                     extra={'user_id': 'unknown', 'chat_id': 'unknown', 'username': 'unknown'})
        raise Exception(f"Failed to download schedule page: {str(e)}")


def parse_groups(page_html: str) -> list[dict]:
    """Достаёт список групп из <script id="groups-data">...</script>."""
    match = _GROUPS_SCRIPT_RE.search(page_html)
    if not match:
        return []
    try:
        raw = html_module.unescape(match.group(1).strip())
        data = json.loads(raw)
    except (ValueError, json.JSONDecodeError) as e:
        logger.error("failed to parse groups-data: %s", str(e),
                     extra={'user_id': 'unknown', 'chat_id': 'unknown', 'username': 'unknown'})
        return []

    groups = []
    for item in data:
        group_id = item.get("id")
        name = item.get("groupName")
        if group_id is not None and name:
            groups.append({"id": group_id, "name": name})
    return groups


def find_group(group_name: str, groups: list[dict]) -> dict | None:
    """Точный поиск группы по названию без учёта регистра."""
    needle = group_name.strip().lower()
    for group in groups:
        if group["name"].strip().lower() == needle:
            return group
    return None


def _text(node) -> str:
    return node.get_text(strip=True) if node else ""


def _direct_children(tag, name):
    return [c for c in tag.find_all(name, recursive=False)]


def _parse_aud_popup(lesson_right) -> dict:
    """Разбирает всплывающую карточку аудитории: номер, корпус, этаж.

    Приоритет отдаём тексту из .aud-popup ("Аудитория: 2210") — там номер
    аудитории идёт без лишнего слова "Аудитория" перед ним, в отличие от
    .aud-num, где оно уже есть в самой подписи кнопки.
    """
    result = {"room": "", "building": None, "floor": None}

    popup = lesson_right.select_one(".aud-popup")
    if popup:
        for p in popup.find_all("p"):
            line = _text(p)
            if line.startswith("Аудитория:"):
                result["room"] = line.split(":", 1)[1].strip()
            elif line.startswith("Корпус:"):
                result["building"] = line.split(":", 1)[1].strip()
            elif "Этаж:" in line:
                result["floor"] = line.split("Этаж:", 1)[1].strip()

    if not result["room"]:
        aud_num = lesson_right.select_one(".aud-num")
        if aud_num:
            result["room"] = re.sub(r"(?i)^аудитория\s*", "", _text(aud_num)).strip()

    return result


def parse_schedule_days(page_html: str) -> dict:
    """
    Парсит блоки .day-block/.lesson-block со страницы расписания.

    Возвращает {date: [lesson, ...]}, где lesson — словарь с ключами
    num, start, end, subject, kind, teacher, room, building, floor.
    Дни без пар на странице просто отсутствуют — их достраивает вызывающий код.
    """
    soup = BeautifulSoup(page_html, "html.parser")
    days = {}

    for day_block in soup.select(".day-block"):
        date_span = day_block.select_one(".weekday-block span")
        if not date_span:
            continue
        date_text = _text(date_span)
        try:
            day_date = datetime.strptime(date_text, "%d.%m.%Y").date()
        except ValueError:
            continue

        lessons = []
        for lesson_block in day_block.select(".lesson-block"):
            start = lesson_block.get("data-lesson-start", "")
            end = lesson_block.get("data-lesson-end", "")

            num_span = lesson_block.select_one(".lesson-num")
            try:
                num = int(_text(num_span)) if num_span else None
            except ValueError:
                num = None

            lesson_left = lesson_block.select_one(".lesson-left")
            subject = _text(lesson_left.find("h4")) if lesson_left else ""
            # Тип занятия — это <p>, лежащий прямо в .lesson-left (не внутри
            # вложенного .lesson-time-num, там тоже есть свой <p> с номером пары).
            kind = ""
            if lesson_left:
                direct_ps = _direct_children(lesson_left, "p")
                if direct_ps:
                    kind = _text(direct_ps[0])

            lesson_right = lesson_block.select_one(".lesson-right")
            teacher = ""
            aud_info = {"room": "", "building": None, "floor": None}
            if lesson_right:
                teacher_span = lesson_right.find("span", recursive=False)
                teacher = _text(teacher_span)
                aud_info = _parse_aud_popup(lesson_right)

            lessons.append({
                "num": num,
                "start": start,
                "end": end,
                "subject": subject,
                "kind": kind,
                "teacher": teacher,
                "room": aud_info["room"],
                "building": aud_info["building"],
                "floor": aud_info["floor"],
            })

        lessons.sort(key=lambda l: l["start"])
        days[day_date] = lessons

    return days


async def fetch_groups(group_id: int = None, org_id: int = ORG_ID) -> list[dict]:
    """Скачивает страницу расписания и достаёт из неё список всех групп."""
    from config import DEFAULT_GROUP_ID
    page_html = await fetch_page(group_id or DEFAULT_GROUP_ID, org_id=org_id)
    return parse_groups(page_html)


async def resolve_group_id(group_name: str) -> dict | None:
    """Находит группу по названию через список групп с портала."""
    groups = await fetch_groups()
    return find_group(group_name, groups)


async def get_week_lessons(group_id: int, monday_date: date, org_id: int = ORG_ID) -> dict:
    """Скачивает и парсит расписание группы на неделю, начинающуюся с monday_date."""
    sunday_date = monday_date + timedelta(days=6)
    page_html = await fetch_page(group_id, date_start=monday_date, date_end=sunday_date, org_id=org_id)
    return parse_schedule_days(page_html)
