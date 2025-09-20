# logging_setup.py

import logging
import logging.handlers
import os

from config import LOGS_DIR

class CustomFormatter(logging.Formatter):
    def format(self, record):
        record.user_id = getattr(record, 'user_id', 'unknown')
        record.chat_id = getattr(record, 'chat_id', 'unknown')
        record.username = getattr(record, 'username', 'unknown')
        return super().format(record)

def setup_logging():
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.INFO)
    
    if not os.path.exists(LOGS_DIR):
        os.makedirs(LOGS_DIR)
    
    log_base = os.path.join(LOGS_DIR, "log")
    file_handler = logging.handlers.TimedRotatingFileHandler(
        log_base, when="midnight", interval=1, backupCount=30, encoding='utf-8'
    )
    file_handler.suffix = "%Y-%m-%d"
    file_handler.setFormatter(CustomFormatter('%(asctime)s - User %(user_id)s (%(username)s) in chat %(chat_id)s: %(message)s'))
    logger.addHandler(file_handler)
    
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(CustomFormatter('%(asctime)s - User %(user_id)s (%(username)s) in chat %(chat_id)s: %(message)s'))
    logger.addHandler(stream_handler)
    
    return logger