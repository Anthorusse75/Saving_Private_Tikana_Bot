# config.py

import platform
import os
import logging
import json
from typing import Union, Any
from dotenv import load_dotenv
import sys

# =======================================================================
# Configuration des Loggers
# ========================================================================

# Setup logger
logger = logging.getLogger("bot")
logger.setLevel(logging.DEBUG)  # default level
handler = logging.StreamHandler()
formatter = logging.Formatter("[%(asctime)s] [%(levelname)s] %(message)s")
handler.setFormatter(formatter)
logger.addHandler(handler)

# Setup logger for discord.py
discord_logger = logging.getLogger("discord")
discord_logger.setLevel(logging.INFO)  # default level
discord_handler = logging.StreamHandler()
discord_handler.setFormatter(formatter)
discord_logger.addHandler(discord_handler)

# Logger for SQL queries
sql_logger = logging.getLogger("sql")
sql_logger.setLevel(logging.INFO)  # default level
sql_handler = logging.StreamHandler()
sql_handler.setFormatter(formatter)
sql_logger.addHandler(sql_handler)

# Setup logger file handler
file_handler = logging.FileHandler("bot.log")
file_handler.setLevel(logging.INFO)  # default level
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)

# ========================================================================
# Détection du système d'exploitation
# ========================================================================
IS_WINDOWS = (platform.system() == "Windows")
base_path = "Conf_files\\" if IS_WINDOWS else "Conf_files/"
l_db_params = os.path.join(base_path, "l_db_params.json")
w_db_params = os.path.join(base_path, "w_db_params.json")
db_file = w_db_params if IS_WINDOWS else l_db_params

# ========================================================================
# Fonctions de chargement de fichiers de configuration
# ========================================================================

ENV_FILE = os.path.join(base_path, "token.env")
if not os.path.exists(ENV_FILE):
    message = "⚠️  Erreur : le fichier conf_bot.env est introuvable."
    padding = 4
    line_length = len(message) + padding * 2
    top_bottom_border = "*" * (line_length + 2)
    empty_line = f"*{' ' * line_length}*"
    centered_message = f"*{' ' * padding}{message}{' ' * padding} *"

    error_message = (
        f"\n{top_bottom_border}\n"
        f"{empty_line}\n"
        f"{centered_message}\n"
        f"{empty_line}\n"
        f"{top_bottom_border}\n"
    )
    print(f"\033[91m{error_message}\033[0m")
    sys.exit(1)

# On charge malgré tout pour récupérer par ex. le TOKEN
load_dotenv(ENV_FILE)

# ========================================================================
# TOKEN
# ========================================================================

GOOD_TOKEN = "bot_token" if IS_WINDOWS else "bot_token"
TOKEN = os.getenv(GOOD_TOKEN)
OWNER_ID = int(os.getenv("owner_id"))

# ========================================================================
# Fonctions de chargement de fichiers de configuration
# ========================================================================

def load_db_config(path: str = db_file) -> dict[str, Any]:
    """
    Fonction synchrone pour charger les paramètres de connexion BDD depuis un fichier JSON.
    """
    with open(path, 'r', encoding='utf-8') as file:
        return json.load(file)