import discord
import logging
import platform
import os
import asyncio
from discord.ext import commands
from config import TOKEN

# Set up logging
logger = logging.getLogger("bot")
logger.setLevel(logging.INFO)  # Default level
handler = logging.StreamHandler()
formatter = logging.Formatter("[%(asctime)s] [%(levelname)s] %(message)s")
handler.setFormatter(formatter)
logger.addHandler(handler)

# Global debug flag (default False)
DEBUG = False

# Define intents
intents = discord.Intents.default()
intents.members = True
intents.message_content = True
intents.guilds = True

bot = commands.Bot(command_prefix="!", intents=intents)
bot.DEBUG = DEBUG  # Set bot attribute for debug

# Auto-load cogs
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

@bot.tree.command(name="set_debug", description="Toggle debug logging")
async def set_debug(interaction: discord.Interaction, value: bool):
    bot.DEBUG = value
    if value:
        logger.setLevel(logging.DEBUG)
        await interaction.response.send_message("Debug logging enabled.", ephemeral=True)
    else:
        logger.setLevel(logging.INFO)
        await interaction.response.send_message("Debug logging disabled.", ephemeral=True)

async def main():
    async with bot:
        await load_cogs()
        await bot.start(TOKEN)

if __name__ == "__main__":
    asyncio.run(main())
