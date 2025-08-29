# FILE: config.py
import os
from dotenv import load_dotenv
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
API_ID = int(os.getenv("API_ID") or 0)
API_HASH = os.getenv("API_HASH")
OWNER_ID = int(os.getenv("OWNER_ID") or 0)
SUPPORT_CHAT = os.getenv("SUPPORT_CHAT")
UPDATE_CHANNEL = os.getenv("UPDATE_CHANNEL")
ARTIST_CHECK_CHAT = os.getenv("ARTIST_CHECK_CHAT")

DOWNLOAD_DIR = os.getenv("DOWNLOAD_DIR", "./downloads")
LOG_CHAT = os.getenv("LOG_CHAT") or OWNER_ID

if not BOT_TOKEN or not API_ID or not API_HASH:
    raise RuntimeError("Required env variables missing. See README.md")
  
