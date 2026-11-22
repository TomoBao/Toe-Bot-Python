import logging
import asyncio
import time
import math
from logging.handlers import RotatingFileHandler
from pathlib import Path

import discord
from discord.ext import commands
from discord import app_commands

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
        self.sync_lock = asyncio.Lock()
        self.next_sync = 0.0
        await self.load_extension("applications")
        await self.load_extension("community")
        guild = discord.Object(id=config.GUILD_ID)
        self.tree.copy_global_to(guild=guild)
        if config.SYNC_ON_STARTUP:
            logger.info(await self.sync_commands())
        else:
            logger.info("Startup sync disabled. Existing registered commands remain available.")

    async def sync_commands(self):
        async with self.sync_lock:
            remaining = self.next_sync - time.monotonic()
            if remaining > 0:
                return f"Sync cooldown: wait {math.ceil(remaining)} seconds."
            self.next_sync = time.monotonic() + 300
            try:
                synced = await self.tree.sync(guild=discord.Object(id=config.GUILD_ID))
            except (discord.HTTPException, discord.RateLimited) as exc:
                if isinstance(exc, discord.RateLimited) or getattr(exc, "status", None) == 429:
                    retry = getattr(exc, "retry_after", None)
                    if retry is None:
                        try:
                            retry = float(exc.response.headers.get("Retry-After", 0))
                        except (AttributeError, ValueError, TypeError):
                            retry = 0
                    self.next_sync = time.monotonic() + max(300, retry or 0)
                    logger.warning("Discord rate-limited command sync; no automatic retry.")
                    return "Discord rate-limited sync. Wait for the cooldown and Discord's limit to expire."
                logger.exception("Command synchronization failed")
                return "Sync failed. Check bot logs and server permissions."
            self.next_sync = time.monotonic() + 300
            return f"Synced {len(synced)} commands to configured guild."


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


@bot.tree.command(name="sync", description="Synchronize slash commands (owner only).")
@app_commands.guild_only()
@app_commands.default_permissions(administrator=True)
async def sync(interaction: discord.Interaction):
    if (
        interaction.guild_id != config.GUILD_ID
        or not config.OWNER_ID
        or interaction.user.id != config.OWNER_ID
    ):
        await interaction.response.send_message("Only the configured owner can sync.", ephemeral=True)
        return
    if bot.sync_lock.locked():
        await interaction.response.send_message("A sync is already in progress.", ephemeral=True)
        return
    await interaction.response.defer(ephemeral=True)
    result = await bot.sync_commands()
    logger.info("%s", result)
    await interaction.followup.send(result, ephemeral=True)


@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    original = getattr(error, "original", error)
    if isinstance(original, discord.RateLimited) or getattr(original, "status", None) == 429:
        logger.warning("Discord rate limit during command; no additional API request attempted.")
        return
    logger.error("Slash command failed", exc_info=(type(error), error, error.__traceback__))


if __name__ == "__main__":
    try:
        bot.run(config.TOKEN, log_handler=None)
    except (discord.HTTPException, discord.RateLimited) as exc:
        if isinstance(exc, discord.RateLimited) or getattr(exc, "status", None) == 429:
            logger.error("Discord API rate limit: stop restarting and wait for the limit to expire.")
        else:
            logger.exception("Discord HTTP failure")
        raise
    except Exception:
        logger.exception("Toe Bot stopped with an error")
        raise
