import discord
import logging
from discord.ext import commands
import config

logging.basicConfig(level=logging.INFO)


class ToeBot(commands.Bot):

    async def setup_hook(self):
        await self.load_extension("applications")

        guild = discord.Object(id=config.GUILD_ID)

        self.tree.copy_global_to(guild=guild)
        synced = await self.tree.sync(guild=guild)

        print(f"Synced {len(synced)} commands.")


bot = ToeBot(
    command_prefix="!",
    intents=discord.Intents.default(),
    allowed_mentions=discord.AllowedMentions.none()
)


@bot.event
async def on_ready():
    print("=" * 40)
    print(f"Toe Bot online as {bot.user}")
    print("Application system loaded.")
    print("=" * 40)

    await bot.change_presence(
        activity=discord.Game(name="TomoBao Server")
    )


@bot.tree.command(
    name="ping",
    description="Check Toe Bot's latency."
)
async def ping(interaction: discord.Interaction):
    await interaction.response.send_message(
        f"Pong! {round(bot.latency * 1000)} ms",
        ephemeral=True
    )


bot.run(config.TOKEN)
