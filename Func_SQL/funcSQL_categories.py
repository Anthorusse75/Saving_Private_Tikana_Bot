import aiomysql
import asyncio
from Func_SQL.db_pool import get_pool  # Assurez-vous que cette fonction est correctement définie

# ───────────────────────────────────────────────────────────────
# Table CategoryAllocations (à créer dans votre DB, par exemple via un script SQL)
# ───────────────────────────────────────────────────────────────
# Exemple de création :
#
# CREATE TABLE IF NOT EXISTS CategoryAllocations (
#     category_id BIGINT PRIMARY KEY,
#     guild_id BIGINT NOT NULL,
#     category_name VARCHAR(255) NOT NULL,
#     allocated_game_guild_id INT NOT NULL,
#     allocated_game_guild VARCHAR(50) NOT NULL
# );
#
# ───────────────────────────────────────────────────────────────

async def allocate_category(category_id: int, guild_id: int, category_name: str, allocated_game_guild_id: int, allocated_game_guild: str):
    """
    Insère ou met à jour l'allocation d'une catégorie à une guilde de jeu.
    Utilise un alias pour les valeurs insérées afin d'éviter l'utilisation de VALUES() qui est dépréciée.
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cursor:
            query = """
            INSERT INTO CategoryAllocations (category_id, guild_id, category_name, allocated_game_guild_id, allocated_game_guild)
            VALUES (%s, %s, %s, %s, %s) AS new
            ON DUPLICATE KEY UPDATE 
                category_name = new.category_name,
                allocated_game_guild_id = new.allocated_game_guild_id,
                allocated_game_guild = new.allocated_game_guild
            """
            await cursor.execute(query, (category_id, guild_id, category_name, allocated_game_guild_id, allocated_game_guild))
            await conn.commit()

async def fetch_category_allocation(category_id: int, guild_id: int):
    """
    Récupère l'allocation d'une catégorie (si existante).
    Retourne None si aucune allocation n'est trouvée.
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cursor:
            query = """
            SELECT allocated_game_guild_id, allocated_game_guild 
            FROM CategoryAllocations 
            WHERE category_id = %s AND guild_id = %s
            """
            await cursor.execute(query, (category_id, guild_id))
            result = await cursor.fetchone()
            return result

async def fetch_all_category_allocations(guild_id: int):
    """
    Récupère toutes les allocations de catégories pour un serveur donné.
    Retourne une liste de tuples :
    (category_id, category_name, allocated_game_guild_id, allocated_game_guild)
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cursor:
            query = """
            SELECT category_id, category_name, allocated_game_guild_id, allocated_game_guild 
            FROM CategoryAllocations 
            WHERE guild_id = %s
            """
            await cursor.execute(query, (guild_id,))
            results = await cursor.fetchall()
            return results
