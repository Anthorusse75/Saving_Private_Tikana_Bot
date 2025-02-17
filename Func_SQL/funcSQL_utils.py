import aiomysql
import asyncio

from Func_SQL.db_pool import get_pool

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
    """
    Fonction asynchrone pour récupérer les informations d'un TextChannel.
    """
    conn = await get_connection()
    if conn is None:
        print("Connexion non établie")
    try:
        async with conn.cursor() as cursor:
            await cursor.execute("""
                SELECT id, jump_url, mention, name, type, guild_id, Webhook_id, short_language, long_language, TCgroup_id, Ggroup_id
                FROM TextChannel
                WHERE id = %s
            """, (channel_id,))
            result = await cursor.fetchone()
            return result
    finally:
        await close_connection(conn)

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