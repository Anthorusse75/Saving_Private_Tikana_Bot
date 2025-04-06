# Func_SQL/funcSQL_utils.py

import aiomysql
import asyncio
import logging

from Func_SQL.db_pool import get_pool
from config import logger

# ========================================================================
# Définition des tables de la base de données
# ========================================================================

TABLES = {
    "TextChannels": [
        "id",
        "jump_url",
        "mention",
        "name",
        "type",
        "guild_id",
        "Webhook_id",
        "short_language",
        "long_language",
        "TCgroup_id",
        "Ggroup_id"
    ]
}

# ========================================================================
# Fonctions de connexion à la base de données
# ========================================================================

async def get_connection() -> aiomysql.Connection:
    """
    Fonction asynchrone pour obtenir une connexion à la base de données.
    """
    pool = await get_pool()
    return await pool.acquire()

async def close_connection(conn: aiomysql.Connection) -> None:
    """
    Fonction asynchrone pour fermer une connexion à la base de données.
    """
    conn.close()
    
# ========================================================================
# Fonctions de requêtes SQL
# ========================================================================

async def fetch_text_channel(channel_id: int) -> tuple:
    logger.debug(f"[fetch_text_channel] Début pour channel_id={channel_id}")
    conn = await get_connection()
    logger.debug(f"[fetch_text_channel] Connexion OK pour channel_id={channel_id}")
    try:
        async with conn.cursor() as cursor:
            logger.debug(f"[fetch_text_channel] Cursor OK, on exécute la requête pour channel_id={channel_id}")

            # Remets ici tes colonnes réelles, par exemple :
            await cursor.execute("""
                SELECT 
                    id,
                    jump_url,
                    mention,
                    name,
                    type,
                    guild_id,
                    Webhook_id,
                    short_language,
                    long_language,
                    TCgroup_id,
                    Ggroup_id
                FROM TextChannel
                WHERE id = %s
            """, (channel_id,))

            result = await cursor.fetchone()
            logger.debug(f"[fetch_text_channel] fetchone terminé => {result}")
            return result
    finally:
        await close_connection(conn)
        logger.debug(f"[fetch_text_channel] Connexion fermée pour channel_id={channel_id}")

# ========================================================================
# Fonctions de verifications SQL
# ========================================================================

async def check_text_channel(channel_id: int) -> bool:
    """
    Fonction asynchrone pour vérifier si un TextChannel existe.
    """
    conn = await get_connection()
    if conn is None:
        print("Connexion non établie")
    try:
        async with conn.cursor() as cursor:
            await cursor.execute("""
                SELECT id
                FROM TextChannel
                WHERE id = %s
            """, (channel_id,))
            result = await cursor.fetchone()
            return bool(result)
    finally:
        await close_connection(conn)