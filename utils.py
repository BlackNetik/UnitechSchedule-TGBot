# utils.py

import re
import json
import os
from datetime import timedelta, timezone

from config import API_KEY_FILE, USERS_JSON_FILE
from logging_setup import setup_logging

logger = setup_logging()
MSK = timezone(timedelta(hours=3))

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
    
    if not re.match(r'^\d{8,10}:[A-Za-z0-9_-]{35}$', api_key):
        logger.error("Invalid API key format in file: %s", API_KEY_FILE, extra={'user_id': 'system', 'chat_id': 'system', 'username': 'unknown'})
        print(f"API-ключ в файле {API_KEY_FILE} имеет неверный формат. Пожалуйста, проверьте ключ и перезапустите программу.")
        exit(1)
    
    return api_key

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

def save_users(users_data):
    try:
        with open(USERS_JSON_FILE, 'w', encoding='utf-8') as f:
            json.dump(users_data, f, indent=4, ensure_ascii=False)
    except Exception as e:
        logger.error("Failed to save users.json: %s", str(e), extra={'user_id': 'system', 'chat_id': 'system', 'username': 'unknown'})