import discord
import logging
import platform
import os
import asyncio
from discord.ext import commands
from config import TOKEN, OWNER_ID  # OWNER_ID: your Discord user ID

# Setup logger
logger = logging.getLogger("bot")
logger.setLevel(logging.INFO)  # default level
handler = logging.StreamHandler()
formatter = logging.Formatter("[%(asctime)s] [%(levelname)s] %(message)s")
handler.setFormatter(formatter)
logger.addHandler(handler)

# Global debug flag
DEBUG = False

# Define bot intents
intents = discord.Intents.default()
intents.members = True
intents.message_content = True
intents.guilds = True

# Create bot instance
bot = commands.Bot(command_prefix="!", intents=intents)
bot.DEBUG = DEBUG

# Owner-only slash command to toggle debug logging
@bot.tree.command(name="set_debug", description="Toggle debug logging (Owner only)")
async def set_debug(interaction: discord.Interaction, value: bool):
    if interaction.user.id != OWNER_ID:
        await interaction.response.send_message("❌ You are not authorized to use this command.", ephemeral=True)
        return
    bot.DEBUG = value
    if value:
        logger.setLevel(logging.DEBUG)
        await interaction.response.send_message("✅ Debug logging enabled.", ephemeral=True)
    else:
        logger.setLevel(logging.INFO)
        await interaction.response.send_message("✅ Debug logging disabled.", ephemeral=True)

# Auto-load all cogs from the "cogs" directory (ignoring __init__.py)
async def load_cogs():
    for filename in os.listdir("./cogs"):
        if filename.endswith(".py") and filename != "__init__.py":
            try:
                await bot.load_extension(f"cogs.{filename[:-3]}")
                logger.info(f"Loaded cog: {filename}")
            except Exception as e:
                logger.error(f"Failed to load cog {filename}: {e}")

@bot.event
async def on_ready():
    await bot.tree.sync()
    logger.info(f"Bot is online as {bot.user} (ID: {bot.user.id})")
    logger.info(f"Operating System: {platform.system()} {platform.release()} ({platform.version()})")
    if bot.guilds:
        guilds = ", ".join(guild.name for guild in bot.guilds)
        logger.info(f"Guilds: {guilds}")
    else:
        logger.info("Bot is not in any guilds yet.")
    logger.info("Slash Commands:")
    for cmd in bot.tree.walk_commands():
        logger.info(f" - {cmd.name}: {cmd.description}")

async def main():
    async with bot:
        await load_cogs()
        await bot.start(TOKEN)

if __name__ == "__main__":
    asyncio.run(main())
