# Func_SQL/db_pool.py

import aiomysql
import asyncio
import logging
# ==> on va créer un nouveau module db_config_loader pour charger la config JSON
from Func_SQL.db_config_loader import load_db_config  # (Chemin à adapter si besoin)

pool = None
logger = logging.getLogger("db_pool")  # Au lieu d'importer LOGGER depuis config

async def init_db_pool():
    global pool
    db_config = load_db_config()  # on récupère la config depuis le nouveau module
    # db_config['db'] = db_config.pop('database', None) # si nécessaire
    try:
        pool = await aiomysql.create_pool(
            **db_config,
            autocommit=True,
            minsize=10,
            maxsize=100,
            charset="utf8mb4"
        )
        logger.info("🔍 Pool de connexions initialisé ✅")
    except Exception as e:
        logger.error(f"🔍 Erreur lors de l'initialisation du pool : {e}")
        raise

async def get_pool():
    global pool
    if pool is None:
        await init_db_pool()
    return pool
