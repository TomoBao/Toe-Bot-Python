"""Community slash commands for Toe Bot."""
import logging
import sqlite3

import discord
from discord import app_commands
from discord.ext import commands

import config

logger = logging.getLogger("toe_bot.community")


def in_server(interaction: discord.Interaction) -> bool:
    return interaction.guild_id == config.GUILD_ID and interaction.guild is not None


def is_manager(interaction: discord.Interaction) -> bool:
    return (
        interaction.user.id == config.OWNER_ID and config.OWNER_ID != 0
    ) or (
        isinstance(interaction.user, discord.Member)
        and interaction.user.guild_permissions.manage_guild
    )


class Community(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="help", description="Show Toe Bot's commands.")
    @app_commands.guild_only()
    async def help_command(self, interaction: discord.Interaction):
        if not in_server(interaction):
            return await interaction.response.send_message("Invalid server.", ephemeral=True)
        embed = discord.Embed(title="Toe Bot • Commands", color=config.EMBED_COLOR)
        embed.description = (
            "**General**\n"
            "`/ping` — Bot latency\n"
            "`/help` — Command list\n"
            "`/userinfo` — Member information\n"
            "`/serverinfo` — Server information\n"
            "`/avatar` — Member avatar\n"
            "`/botinfo` — Bot information\n"
            "`/application-status` — Your applications\n\n"
            "**Staff**\n"
            "`/announce` — Post an announcement\n"
            "`/setup-applications` — Create the application panel"
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="userinfo", description="View a server member's information.")
    @app_commands.guild_only()
    @app_commands.describe(member="Member to inspect (defaults to you)")
    async def userinfo(self, interaction: discord.Interaction, member: discord.Member | None = None):
        if not in_server(interaction):
            return await interaction.response.send_message("Invalid server.", ephemeral=True)
        member = member or interaction.user
        embed = discord.Embed(title="Member Information", color=config.EMBED_COLOR)
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name="Name", value=discord.utils.escape_markdown(str(member)), inline=False)
        embed.add_field(name="User ID", value=str(member.id))
        embed.add_field(name="Joined Discord", value=discord.utils.format_dt(member.created_at, "D"))
        if member.joined_at:
            embed.add_field(name="Joined Server", value=discord.utils.format_dt(member.joined_at, "D"))
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="serverinfo", description="View information about this server.")
    @app_commands.guild_only()
    async def serverinfo(self, interaction: discord.Interaction):
        if not in_server(interaction):
            return await interaction.response.send_message("Invalid server.", ephemeral=True)
        guild = interaction.guild
        embed = discord.Embed(title="Server Information", color=config.EMBED_COLOR)
        embed.add_field(name="Server", value=discord.utils.escape_markdown(guild.name), inline=False)
        embed.add_field(name="Server ID", value=str(guild.id))
        embed.add_field(name="Members", value=str(guild.member_count or "Unavailable"))
        embed.add_field(name="Channels", value=str(len(guild.channels)))
        embed.add_field(name="Roles", value=str(len(guild.roles)))
        embed.add_field(name="Created", value=discord.utils.format_dt(guild.created_at, "D"))
        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="avatar", description="Show a member's avatar.")
    @app_commands.guild_only()
    @app_commands.describe(member="Member (defaults to you)")
    async def avatar(self, interaction: discord.Interaction, member: discord.Member | None = None):
        if not in_server(interaction):
            return await interaction.response.send_message("Invalid server.", ephemeral=True)
        member = member or interaction.user
        embed = discord.Embed(title=f"{member.display_name}'s Avatar", color=config.EMBED_COLOR)
        embed.set_image(url=member.display_avatar.url)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="botinfo", description="Show information about Toe Bot.")
    @app_commands.guild_only()
    async def botinfo(self, interaction: discord.Interaction):
        if not in_server(interaction):
            return await interaction.response.send_message("Invalid server.", ephemeral=True)
        embed = discord.Embed(
            title="Toe Bot",
            description="TomoBao's community and application management bot.",
            color=config.EMBED_COLOR,
        )
        embed.add_field(name="Library", value=f"discord.py {discord.__version__}")
        embed.add_field(name="Latency", value=f"{round(self.bot.latency * 1000)} ms")
        embed.add_field(name="Commands", value="Community tools and developer/alpha tester applications", inline=False)
        if self.bot.user:
            embed.set_thumbnail(url=self.bot.user.display_avatar.url)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="application-status", description="Check the status of your applications.")
    @app_commands.guild_only()
    async def application_status(self, interaction: discord.Interaction):
        if not in_server(interaction):
            return await interaction.response.send_message("Invalid server.", ephemeral=True)
        from applications import db, submit_lock
        try:
            async with submit_lock:
                records = db.execute(
                    "SELECT kind, status FROM applications WHERE user_id = ? AND guild_id = ? ORDER BY rowid DESC LIMIT 10",
                    (interaction.user.id, interaction.guild_id),
                ).fetchall()
        except sqlite3.Error:
            logger.exception("Could not read application status")
            return await interaction.response.send_message(
                "Unable to check your applications right now.", ephemeral=True
            )
        if not records:
            return await interaction.response.send_message(
                "You have not submitted any applications.", ephemeral=True
            )
        embed = discord.Embed(title="Your Applications", color=config.EMBED_COLOR)
        for kind, status in records:
            embed.add_field(name=kind, value=status, inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="announce", description="Post a staff announcement to a channel.")
    @app_commands.guild_only()
    @app_commands.describe(channel="Channel to post in", message="Announcement text")
    @app_commands.default_permissions(manage_guild=True)
    async def announce(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
        message: app_commands.Range[str, 1, 1800],
    ):
        if not in_server(interaction) or not is_manager(interaction):
            return await interaction.response.send_message(
                "Only the configured owner or server managers can announce.", ephemeral=True
            )
        if channel.guild.id != interaction.guild_id:
            return await interaction.response.send_message("Invalid channel.", ephemeral=True)
        me = interaction.guild.me
        if me is None or not (
            channel.permissions_for(me).view_channel
            and channel.permissions_for(me).send_messages
            and channel.permissions_for(me).embed_links
        ):
            return await interaction.response.send_message(
                "Toe Bot needs View Channel, Send Messages and Embed Links there.", ephemeral=True
            )
        embed = discord.Embed(
            title="📢 Announcement",
            description=discord.utils.escape_mentions(message),
            color=config.EMBED_COLOR,
            timestamp=discord.utils.utcnow(),
        )
        embed.set_footer(text="TomoBao • Community Announcement")
        await interaction.response.defer(ephemeral=True)
        try:
            await channel.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())
        except discord.HTTPException:
            logger.exception("Failed to post announcement")
            return await interaction.followup.send(
                "Could not post the announcement. Check channel permissions.", ephemeral=True
            )
        await interaction.followup.send(f"Announcement posted in {channel.mention}.", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Community(bot))
