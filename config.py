import os
from os import getenv

# ---------------CONFIG---------------------------------
API_ID = int(os.environ.get("API_ID", "6886135"))
# ------------------------------------------------
API_HASH = os.environ.get("API_HASH", "ee20a1c8a8e44eaa638b7254cbcc3012")
# ------------------------------------------------
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8525803667:AAEjpylk_qaZ62O_gIZmch46S8VQNYxcY1M")
# ------------------------------------------------
BOT_USERNAME = os.environ.get("BOT_USERNAME", "@Natking_uploader_bot")
# ------------------------------------------------
OWNER_ID = int(os.environ.get("OWNER_ID", "2118600611"))
# ------------------------------------------------

SUDO_USERS = list(map(int, getenv("SUDO_USERS", "2118600611").split()))
# ------------------------------------------------
CHANNEL_ID = int(os.environ.get("CHANNEL_ID", "-1003744110162"))
# ------------------------------------------------
MONGO_URL = os.environ.get("MONGO_URL", "mongodb+srv://nattu:nattu@cluster0.quvds.mongodb.net/?appName=Cluster0")
# -----------------------------------------------
PREMIUM_LOGS = int(os.environ.get("PREMIUM_LOGS", "-1003744110162"))
