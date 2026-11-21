import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

import discord
from discord.ext import commands

import config

BASE_DIR = Path(__file__).resolve().parent
LOG_DIR = BASE_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)

log_format = logging.Formatter(
    "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)

file_handler = RotatingFileHandler(
    LOG_DIR / "toe-bot.log",
    maxBytes=2_000_000,
    backupCount=3,
    encoding="utf-8",
)
file_handler.setFormatter(log_format)

console_handler = logging.StreamHandler()
console_handler.setFormatter(log_format)

logging.basicConfig(
    level=logging.INFO,
    handlers=[file_handler, console_handler],
    force=True,
)

logger = logging.getLogger("toe_bot")


class ToeBot(commands.Bot):
    async def setup_hook(self):
        await self.load_extension("applications")
        await self.load_extension("community")
        guild = discord.Object(id=config.GUILD_ID)
        self.tree.copy_global_to(guild=guild)
        synced = await self.tree.sync(guild=guild)
        logger.info("Synced %d commands to configured guild", len(synced))


bot = ToeBot(
    command_prefix="!",
    intents=discord.Intents.default(),
    allowed_mentions=discord.AllowedMentions.none(),
)


@bot.event
async def on_ready():
    logger.info("Toe Bot online as %s", bot.user)
    logger.info("Application system loaded")
    await bot.change_presence(
        activity=discord.Game(name="TomoBao Server")
    )


@bot.tree.command(name="ping", description="Check Toe Bot's latency.")
async def ping(interaction: discord.Interaction):
    await interaction.response.send_message(
        f"Pong! {round(bot.latency * 1000)} ms",
        ephemeral=True,
    )


if __name__ == "__main__":
    try:
        bot.run(config.TOKEN, log_handler=None)
    except Exception:
        logger.exception("Toe Bot stopped with an error")
        raise
