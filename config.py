# config.py

BOT_VERSION = "2.0"
LAST_UPDATED = "07.09.2026"

FEEDBACK_WAITING = 1
DAY_SELECTION = 2
CHANGE_GROUP_WAITING = 3

LOGS_DIR = "Logs"
API_KEY_FILE = 'api_key_journal_unitech.txt'
USERS_JSON_FILE = 'users.json'
DEVELOPER_CHAT_ID = "-4956911463"  # ID чата разработчика. Измените на свой ID в config.py для своего проекта
DEVELOPER_USERNAME = "@BlackNetRus"  # Username разработчика для обратной связи

# Портал расписания МИИГАиК (https://study.miigaik.ru), заменивший старый
# es.unitech-mo.ru. orgId — это конкретный институт/филиал в системе МИИГАиК
# (2 = ТУ им. А.А. Леонова), а не сам МИИГАиК целиком — если понадобится
# расписание другого филиала, узнайте его orgId так же, как groupId: открыв
# study.miigaik.ru и посмотрев на параметр orgId в адресной строке.
PORTAL_BASE_URL = "https://study.miigaik.ru"
ORG_ID = 2
DEFAULT_GROUP_ID = 1671
DEFAULT_GROUP_NAME = "ПИ-23"
