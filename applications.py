
import asyncio
import logging
import sqlite3
import discord

from discord import app_commands
from discord.ext import commands

import config

logger = logging.getLogger('toe_bot.applications')


# ==========================================
# DATABASE
# ==========================================

db = sqlite3.connect(config.DATABASE_PATH)

db.execute("""
CREATE TABLE IF NOT EXISTS applications (
    message_id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL,
    guild_id INTEGER NOT NULL,
    kind TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'Pending',
    reviewer_id INTEGER
)
""")

db.commit()

review_lock = asyncio.Lock()
submit_lock = asyncio.Lock()


def is_staff(member):
    return (
        isinstance(member, discord.Member)
        and (
            member.guild_permissions.administrator
            or config.STAFF_ROLE_ID
            in [role.id for role in member.roles]
        )
    )


# ==========================================
# QUESTIONS
# ==========================================

QUESTIONS = {
    "Developer": [
        "Why do you want to be a developer?",
        "What programming languages do you use?",
        "Describe your development experience.",
        "What would you like to work on?",
        "GitHub profile (optional)"
    ],

    "Alpha Tester": [
        "Why do you want to be an alpha tester?",
        "Do you have testing experience?",
        "What operating system do you use?",
        "Can you provide detailed bug reports?",
        "Do you agree to the testing rules?"
    ]
}


# ==========================================
# APPLICATION MODAL
# ==========================================

class ApplicationModal(discord.ui.Modal):

    def __init__(self, kind):
        super().__init__(
            title=f"{kind} Application",
            timeout=600
        )

        self.kind = kind
        self.answers = []

        for index, question in enumerate(QUESTIONS[kind]):

            field = discord.ui.TextInput(
                label=question,
                style=discord.TextStyle.paragraph,
                placeholder="Enter your answer...",
                max_length=600,
                required=not (
                    kind == "Developer" and index == 4
                )
            )

            self.answers.append(field)
            self.add_item(field)

    async def on_submit(self, interaction):

        if interaction.guild_id != config.GUILD_ID:
            await interaction.response.send_message(
                "Invalid server.",
                ephemeral=True
            )
            return

        await interaction.response.defer(
            ephemeral=True,
            thinking=True
        )

        async with submit_lock:

            pending = db.execute(
                """
                SELECT message_id FROM applications
                WHERE user_id = ?
                AND guild_id = ?
                AND kind = ?
                AND status = 'Pending'
                """,
                (
                    interaction.user.id,
                    interaction.guild_id,
                    self.kind
                )
            ).fetchone()

            if pending:
                await interaction.followup.send(
                    "You already have a pending application.",
                    ephemeral=True
                )
                return

            channel = interaction.guild.get_channel(
                config.APPLICATION_LOG_CHANNEL_ID
            )

            if (
                not isinstance(channel, discord.TextChannel)
                or channel.permissions_for(
                    interaction.guild.default_role
                ).view_channel
                or channel.permissions_for(
                    interaction.user
                ).view_channel
                and not is_staff(interaction.user)
            ):
                await interaction.followup.send(
                    "Private application logs are not configured.",
                    ephemeral=True
                )
                return

            embed = discord.Embed(
                title=f"New {self.kind} Application",
                color=config.EMBED_COLOR,
                timestamp=discord.utils.utcnow()
            )

            embed.set_author(
                name=str(interaction.user),
                icon_url=interaction.user.display_avatar.url
            )

            embed.add_field(
                name="Applicant",
                value=interaction.user.mention,
                inline=False
            )

            for answer in self.answers:
                embed.add_field(
                    name=answer.label,
                    value=answer.value or "Not provided",
                    inline=False
                )

            embed.add_field(
                name="Status",
                value="Pending",
                inline=False
            )

            embed.set_footer(
                text="TomoBao Application System"
            )

            message = None

            try:
                message = await channel.send(
                    embed=embed,
                    allowed_mentions=discord.AllowedMentions.none()
                )

                db.execute(
                    """
                    INSERT INTO applications (
                        message_id,
                        user_id,
                        guild_id,
                        kind
                    )
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        message.id,
                        interaction.user.id,
                        interaction.guild_id,
                        self.kind
                    )
                )

                db.commit()

                await message.edit(view=ReviewView())

            except (discord.HTTPException, sqlite3.Error):

                db.rollback()

                if message:
                    db.execute(
                        "DELETE FROM applications WHERE message_id = ?",
                        (message.id,)
                    )
                    db.commit()

                    try:
                        await message.delete()
                    except discord.HTTPException:
                        pass

                await interaction.followup.send(
                    "Submission failed. Contact an administrator.",
                    ephemeral=True
                )
                return

            await interaction.followup.send(
                "Application submitted successfully! "
                "Please wait for staff to review it.",
                ephemeral=True
            )


# ==========================================
# PUBLIC APPLICATION BUTTONS
# ==========================================

class ApplicationView(discord.ui.View):

    def __init__(self):
        super().__init__(timeout=None)

    async def interaction_check(self, interaction):
        if interaction.guild_id != config.GUILD_ID:
            await interaction.response.send_message(
                "Invalid server.",
                ephemeral=True
            )
            return False

        return True

    @discord.ui.button(
        label="Apply to be a developer",
        style=discord.ButtonStyle.success,
        custom_id="toe:apply:developer"
    )
    async def developer(self, interaction, button):

        await interaction.response.send_modal(
            ApplicationModal("Developer")
        )

    @discord.ui.button(
        label="Apply to be an alpha tester",
        emoji="🧪",
        style=discord.ButtonStyle.primary,
        custom_id="toe:apply:alpha"
    )
    async def alpha(self, interaction, button):

        await interaction.response.send_modal(
            ApplicationModal("Alpha Tester")
        )


# ==========================================
# STAFF REVIEW SYSTEM
# ==========================================

class ReviewView(discord.ui.View):

    def __init__(self):
        super().__init__(timeout=None)

    async def review(self, interaction, accepted):

        if (
            interaction.guild_id != config.GUILD_ID
            or interaction.channel_id
            != config.APPLICATION_LOG_CHANNEL_ID
            or not is_staff(interaction.user)
        ):
            await interaction.response.send_message(
                "You cannot review applications.",
                ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True)

        async with review_lock:

            application = db.execute(
                """
                SELECT user_id, kind, status
                FROM applications
                WHERE message_id = ?
                AND guild_id = ?
                """,
                (
                    interaction.message.id,
                    interaction.guild_id
                )
            ).fetchone()

            if not application:
                await interaction.followup.send(
                    "Application not found.",
                    ephemeral=True
                )
                return

            user_id, kind, status = application

            if status != "Pending":
                await interaction.followup.send(
                    f"Already {status.lower()}.",
                    ephemeral=True
                )
                return

            if user_id == interaction.user.id:
                await interaction.followup.send(
                    "You cannot review your own application.",
                    ephemeral=True
                )
                return

            member = None

            try:
                member = await interaction.guild.fetch_member(
                    user_id
                )

            except discord.NotFound:
                if accepted:
                    await interaction.followup.send(
                        "The applicant is no longer in the server.",
                        ephemeral=True
                    )
                    return

            except discord.HTTPException:
                await interaction.followup.send(
                    "Unable to retrieve the applicant.",
                    ephemeral=True
                )
                return

            if accepted:

                role_id = (
                    config.DEVELOPER_ROLE_ID
                    if kind == "Developer"
                    else config.ALPHA_TESTER_ROLE_ID
                )

                role = interaction.guild.get_role(role_id)

                dangerous_permissions = [
                    "administrator",
                    "manage_guild",
                    "manage_roles",
                    "manage_channels",
                    "manage_webhooks",
                    "manage_messages",
                    "kick_members",
                    "ban_members",
                    "moderate_members",
                    "mention_everyone",
                    "manage_threads"
                ]

                if (
                    role is None
                    or role.managed
                    or role.is_default()
                    or role.id == config.STAFF_ROLE_ID
                    or not role.is_assignable()
                    or any(
                        getattr(role.permissions, permission)
                        for permission in dangerous_permissions
                    )
                ):
                    await interaction.followup.send(
                        "The application role is unsafe "
                        "or cannot be assigned.",
                        ephemeral=True
                    )
                    return

                # Do not assign roles that grant privileged
                # permissions through channel overrides.
                for channel in interaction.guild.channels:
                    overwrite = channel.overwrites_for(role)

                    if any(
                        getattr(overwrite, permission, None)
                        is True
                        for permission in dangerous_permissions
                    ):
                        await interaction.followup.send(
                            "Unsafe channel permission override.",
                            ephemeral=True
                        )
                        return

                try:
                    await member.add_roles(
                        role,
                        reason="Approved TomoBao application"
                    )

                except discord.HTTPException:
                    await interaction.followup.send(
                        "Cannot assign role. Check permissions.",
                        ephemeral=True
                    )
                    return

            final_status = (
                "Accepted" if accepted else "Rejected"
            )

            db.execute(
                """
                UPDATE applications
                SET status = ?, reviewer_id = ?
                WHERE message_id = ?
                """,
                (
                    final_status,
                    interaction.user.id,
                    interaction.message.id
                )
            )

            db.commit()

            embed = interaction.message.embeds[0].copy()

            embed.color = (
                discord.Color.green()
                if accepted
                else discord.Color.red()
            )

            for index, field in enumerate(embed.fields):
                if field.name == "Status":
                    embed.set_field_at(
                        index,
                        name="Status",
                        value=final_status,
                        inline=False
                    )
                    break

            embed.add_field(
                name="Reviewed By",
                value=interaction.user.mention,
                inline=False
            )

            try:
                await interaction.message.edit(
                    embed=embed,
                    view=None
                )
            except discord.HTTPException:
                pass

            # Send the applicant a private notification.

            dm_sent = False

            if member:

                result_embed = discord.Embed(
                    title=f"Application {final_status}",
                    description=(
                        f"Your {kind} application for "
                        f"the TomoBao Server has been "
                        f"{final_status.lower()}."
                    ),
                    color=embed.color
                )

                try:
                    await member.send(embed=result_embed)
                    dm_sent = True
                except discord.HTTPException:
                    pass

            await interaction.followup.send(
                f"Application {final_status.lower()}."
                + (
                    " Applicant notified."
                    if dm_sent else
                    " Applicant DM unavailable."
                ),
                ephemeral=True
            )

    @discord.ui.button(
        label="Accept",
        emoji="✅",
        style=discord.ButtonStyle.success,
        custom_id="toe:review:accept"
    )
    async def accept(self, interaction, button):
        await self.review(interaction, True)

    @discord.ui.button(
        label="Reject",
        emoji="❌",
        style=discord.ButtonStyle.danger,
        custom_id="toe:review:reject"
    )
    async def reject(self, interaction, button):
        await self.review(interaction, False)


# ==========================================
# SLASH COMMAND
# ==========================================

class Applications(commands.Cog):

    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(
        name="setup-applications",
        description="Create the application panel."
    )
    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    async def setup_applications(
        self,
        interaction: discord.Interaction
    ):

        same_guild = interaction.guild_id == config.GUILD_ID
        is_admin = (
            isinstance(interaction.user, discord.Member)
            and interaction.user.guild_permissions.administrator
        )
        owner_id = interaction.guild.owner_id if interaction.guild else None

        # A partial guild cache can leave owner_id unset.
        # Fetch authoritative guild metadata before checking ownership.
        if same_guild and owner_id is None:
            try:
                fetched_guild = await interaction.client.fetch_guild(
                    interaction.guild_id
                )
                owner_id = fetched_guild.owner_id
            except discord.HTTPException:
                logger.exception("Unable to fetch guild owner for setup")

        # An explicitly configured owner can run setup even when Discord
        # does not provide guild owner metadata.
        configured_owner_id = config.OWNER_ID
        is_owner = (
            (configured_owner_id != 0 and interaction.user.id == configured_owner_id)
            or (owner_id is not None and interaction.user.id == owner_id)
        )

        logger.info(
            "setup-applications: guild_match=%s owner_match=%s "
            "administrator=%s owner_id_available=%s",
            same_guild, is_owner, is_admin, owner_id is not None
        )

        if not same_guild or not (is_owner or is_admin):
            logger.warning(
                "setup-applications denied: guild_match=%s "
                "owner_match=%s administrator=%s owner_id_available=%s",
                same_guild, is_owner, is_admin, owner_id is not None
            )
            await interaction.response.send_message(
                "Only the server owner or an administrator can use this command.",
                ephemeral=True
            )
            return

        embed = discord.Embed(
            title="TomoBao Applications",
            description=(
                "**Want to help develop TomoBao projects?**\n\n"
                "We are looking for developers! Press the "
                "button below and answer a few questions "
                "about your experience and interests.\n\n"
                "**Want early access to upcoming updates?**\n\n"
                "Apply to become an Alpha Tester! Help us "
                "discover bugs and improve our projects.\n\n"
                "Your answers are shared with authorized "
                "reviewers. Do not include personal details, "
                "passwords, or tokens."
            ),
            color=config.EMBED_COLOR
        )

        if interaction.guild.icon:
            embed.set_thumbnail(
                url=interaction.guild.icon.url
            )

        embed.set_footer(
            text="TomoBao • Application System"
        )

        await interaction.response.defer(ephemeral=True)

        await interaction.channel.send(
            embed=embed,
            view=ApplicationView()
        )

        await interaction.followup.send(
            "Application panel created!",
            ephemeral=True
        )


# ==========================================
# REGISTER PERSISTENT VIEWS
# ==========================================

async def setup(bot):

    bot.add_view(ApplicationView())
    bot.add_view(ReviewView())

    await bot.add_cog(Applications(bot))
