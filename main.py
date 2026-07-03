import discord
import d20
import re
import os
import json
import asyncio
import modiphius
from repository import ConfigRepository, RollHistoryRepository
from discord.ext import commands
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

intents = discord.Intents.all()
command_prefix = ";;"

bot = commands.Bot(
    command_prefix=[command_prefix], intents=intents, help_command=None
)


# Default server config; also the shape every stored config is normalised to.
DEFAULT_CONFIG = {"dump_channel_id": 0, "thread_dump_target": "dump_channel"}

# thread_dump_target value -> human label shown in the settings embed.
THREAD_TARGET_LABELS = {
    "dump_channel": "Dump channel",
    "parent_channel": "Parent channel",
}


def load_server_config(guild_id) -> dict:
    """Return this guild's config merged over ``DEFAULT_CONFIG``."""
    row = ConfigRepository().get_config(guild_id)
    if row is None:
        return dict(DEFAULT_CONFIG)
    stored = json.loads(row[0])
    return {
        "dump_channel_id": int(stored.get("dump_channel_id", 0) or 0),
        "thread_dump_target": stored.get(
            "thread_dump_target", DEFAULT_CONFIG["thread_dump_target"]
        ),
    }


class SettingsView(discord.ui.View):
    """Interactive settings panel.

    Dropdowns only stage changes into ``self.pending``; nothing is written to
    the database until the Save button is pressed. The embed re-renders after
    every interaction so the pending-vs-saved diff is always visible.
    """

    def __init__(self, guild_id: int, author_id: int, saved: dict):
        super().__init__(timeout=180)
        self.guild_id = guild_id
        self.author_id = author_id
        self.saved = dict(saved)
        self.pending = dict(saved)
        self.message = None  # set by the command once the panel is sent

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message(
                f"This settings panel isn't yours — run "
                f"`{command_prefix}settings` yourself.",
                ephemeral=True,
            )
            return False
        if not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message(
                "You need the **Manage Server** permission to change settings.",
                ephemeral=True,
            )
            return False
        return True

    @staticmethod
    def _dump_channel_str(config: dict) -> str:
        channel_id = config["dump_channel_id"]
        return f"<#{channel_id}>" if channel_id else "*Not set*"

    def build_embed(self, note: str = None) -> discord.Embed:
        embed = discord.Embed(
            title="⚙️ Inline Roller Settings",
            color=discord.Color.blurple(),
        )
        embed.add_field(
            name="Dump channel",
            value=self._dump_channel_str(self.saved),
            inline=True,
        )
        embed.add_field(
            name="Thread rolls dump to",
            value=THREAD_TARGET_LABELS[self.saved["thread_dump_target"]],
            inline=True,
        )
        if self.pending != self.saved:
            lines = []
            if self.pending["dump_channel_id"] != self.saved["dump_channel_id"]:
                lines.append(
                    f"• Dump channel → {self._dump_channel_str(self.pending)}"
                )
            if self.pending["thread_dump_target"] != \
                    self.saved["thread_dump_target"]:
                lines.append(
                    "• Thread rolls → "
                    f"{THREAD_TARGET_LABELS[self.pending['thread_dump_target']]}"
                )
            embed.add_field(
                name="⚠️ Unsaved changes",
                value="\n".join(lines) + "\n**Click Save to apply.**",
                inline=False,
            )
        if note:
            embed.set_footer(text=note)
        return embed

    async def _refresh(self, interaction: discord.Interaction,
                       note: str = None):
        await interaction.response.edit_message(
            embed=self.build_embed(note), view=self
        )

    @discord.ui.select(
        cls=discord.ui.ChannelSelect,
        channel_types=[discord.ChannelType.text],
        placeholder="Dump channel…",
        min_values=1,
        max_values=1,
        row=0,
    )
    async def dump_channel_select(self, interaction: discord.Interaction,
                                  select: discord.ui.ChannelSelect):
        self.pending["dump_channel_id"] = select.values[0].id
        await self._refresh(interaction)

    @discord.ui.select(
        placeholder="When rolled in a thread, dump to…",
        min_values=1,
        max_values=1,
        row=1,
        options=[
            discord.SelectOption(
                label="Dump channel", value="dump_channel",
                description="Thread rolls go to the configured dump channel."
            ),
            discord.SelectOption(
                label="Parent channel", value="parent_channel",
                description="Thread rolls go to the thread's parent channel."
            ),
        ],
    )
    async def thread_target_select(self, interaction: discord.Interaction,
                                   select: discord.ui.Select):
        self.pending["thread_dump_target"] = select.values[0]
        await self._refresh(interaction)

    @discord.ui.button(label="Save", style=discord.ButtonStyle.success, row=2)
    async def save_button(self, interaction: discord.Interaction,
                          button: discord.ui.Button):
        ConfigRepository().set_config(
            self.guild_id,
            self.pending["dump_channel_id"],
            self.pending["thread_dump_target"],
        )
        self.saved = dict(self.pending)
        await self._refresh(interaction, note="✅ Settings saved.")

    @discord.ui.button(
        label="Reset to defaults", style=discord.ButtonStyle.secondary, row=2
    )
    async def reset_button(self, interaction: discord.Interaction,
                           button: discord.ui.Button):
        self.pending = dict(DEFAULT_CONFIG)
        await self._refresh(
            interaction, note="Defaults staged — click Save to apply."
        )

    async def on_timeout(self):
        for child in self.children:
            child.disabled = True
        if self.message is not None:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass


@bot.command(name="settings")
@commands.guild_only()
@commands.has_permissions(manage_guild=True)
async def settings(ctx):
    saved = load_server_config(ctx.guild.id)
    view = SettingsView(ctx.guild.id, ctx.author.id, saved)
    view.message = await ctx.send(embed=view.build_embed(), view=view)


@settings.error
async def settings_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send(
            "You need the **Manage Server** permission to use this."
        )
    elif isinstance(error, commands.NoPrivateMessage):
        await ctx.send("This command only works inside a server.")


def build_help_embed() -> discord.Embed:
    embed = discord.Embed(
        title="Inline Roller — Help",
        description=(
            "Put dice in **double brackets** inside a proxied "
            "(Tupperbox) message. The bot rolls it, swaps it inline for "
            "the result, and posts the full breakdown to the dump channel.\n"
            "Example: `[[1d20+5]]` → 【 18 】"
        ),
        color=discord.Color.gold(),
    )
    embed.add_field(
        name="Standard dice",
        value=(
            "`[[1d20]]` · `[[2d6+3]]` · `[[1d100]]`\n"
            "Add a comment: `[[1d20+5 attack]]`"
        ),
        inline=False,
    )
    embed.add_field(
        name="Modiphius 2d20 test",
        value=(
            "`[[<n>d20 t<TN> f<focus> c<range>]]`\n"
            "• `t` target number — **required**\n"
            "• `f` focus — optional, default `1` "
            "(roll ≤ focus = 2 successes, ≤ TN = 1 success)\n"
            "• `c` complication range — optional, default `0` "
            "(`c1` → complication on 19-20, `c2` → 18-20)\n"
            "Example: `[[2d20f3t12c1]]`"
        ),
        inline=False,
    )
    embed.add_field(
        name="Challenge dice",
        value=(
            "`[[<n>cd]]` rolls a pool of d6 for results & effects.\n"
            "Example: `[[6cd]]`"
        ),
        inline=False,
    )
    embed.add_field(
        name="Manage a roll",
        value="React to a proxied roll message: ❌ delete · 📝 edit",
        inline=False,
    )
    embed.add_field(
        name="Commands",
        value=(
            f"`{command_prefix}settings` — set the dump channel & thread "
            "behavior *(Manage Server)*\n"
            f"`{command_prefix}help` — show this message"
        ),
        inline=False,
    )
    return embed


@bot.command(name="help")
async def help_command(ctx):
    await ctx.send(embed=build_help_embed())


@bot.event
async def on_ready():
    print("We have logged in as {0.user}".format(bot))


@bot.event
async def on_reaction_add(reaction, user):
    if user.bot:
        return
    if reaction.message.webhook_id is None:
        return
    if reaction.emoji not in ["❌", "📝"]:
        return
    webhook_name = f"{bot.application.name}hook"
    webhook = await bot.fetch_webhook(reaction.message.webhook_id)
    if webhook.name != webhook_name:
        return
    if reaction.emoji == "❌":
        await delete_reaction_message(reaction, user, webhook)
        return
    if reaction.emoji == "📝":
        await edit_reaction_message(reaction, user, webhook)
        return


@bot.event
async def on_message(message):
    await bot.process_commands(message)
    await edit_by_tul_edit(message)
    if not hasattr(message, "webhook_id") or message.webhook_id is None:
        return
    webhook = await bot.fetch_webhook(message.webhook_id)
    if webhook.name != "Tupperhook":
        return

    content = message.content
    inline_rolls = find_inline_roll(content)
    if len(inline_rolls) == 0:
        return
    display_name = message.author.display_name
    avatar = message.author.avatar
    channel_mention = message.channel.mention  # where the roll happened

    config = load_server_config(message.guild.id)
    dump_channel_id = config["dump_channel_id"]
    thread_target = config["thread_dump_target"]

    channel = message.channel
    thread = None
    if getattr(message.channel, "parent", None) is not None:
        channel = message.channel.parent  # webhook posts to the parent
        thread = message.channel

    # Resolve where the full-result dump is sent.
    if thread is not None and thread_target == "parent_channel":
        dump_channel = channel  # the thread's parent
    elif dump_channel_id:
        dump_channel = await bot.fetch_channel(dump_channel_id)
    elif thread is not None:
        dump_channel = channel  # no dump channel set -> fall back to parent
    else:
        await message.channel.send(
            "No dump channel set.\n" +
            "Please roll inside a thread, or set one first.\n" +
            f"Use `{command_prefix}settings` to configure it."
        )
        return

    webhook = await create_webhook_by_channel(channel, bot.application.name)

    result_texts = []
    histories_list = []
    for inline_roll in inline_rolls:
        modiphius_result = modiphius.roll(inline_roll)
        if modiphius_result is not None:
            result_texts.append(modiphius_result["full_text"])
            content = content.replace(
                f"[[{inline_roll}]]", modiphius_result["inline"], 1
            )
            histories_list.append({
                "message": message,
                "modiphius": modiphius_result,
                "command": inline_roll
            })
            continue
        result = d20.roll(inline_roll, allow_comments=True)
        result_text = f"{result.comment}: {result}" if result.comment else \
            str(result)
        result_texts.append(result_text)
        crit = ""
        if result.crit == 2:
            crit = "💀"
        if result.crit == 1:
            crit = "💥"
        else:
            pass
        comment = f" {result.comment}" if result.comment else ""
        inline_replacement = f"【 {result.total}{crit}{comment} 】"
        content = content.replace(f"[[{inline_roll}]]", inline_replacement, 1)
        histories_list.append({
            "message": message,
            "d20_roll": result,
            "command": inline_roll
        })
    full_result = '\n'.join(result_texts)
    asyncio.create_task(insert_roll_histories(histories_list))

    dump_message = await dump_channel.send(
        f"**{display_name}** in {channel_mention}:" + "\n" +
        full_result
    )

    dump_message_url = f"[`🔻`]({dump_message.jump_url})"
    content = f"{content} {dump_message_url}"

    if thread is not None:
        await send_to_thread_by_webhook(
            thread, content, avatar, display_name, webhook
        )
    else:
        await send_to_channel_by_webhook(
            content, avatar, display_name, webhook
        )

    await message.delete()


# Create webhook based on bot name and channel.
# If webhook already exists, return existing webhook.
async def create_webhook_by_channel(channel, bot_name):
    webhook_name = f"{bot_name}hook"
    webhooks = await channel.webhooks()
    for webhook in webhooks:
        if webhook.name == webhook_name and webhook.token is not None:
            return webhook
    return await channel.create_webhook(name=webhook_name)


# Send message to channle by webhook
async def send_to_channel_by_webhook(content, avatar, username, webhook):
    return await webhook.send(
        content=content,
        username=username,
        avatar_url=avatar
    )


# Send message to thread by webhook
async def send_to_thread_by_webhook(thread, content, avatar, username,
                                    webhook):
    return await webhook.send(
        content=content,
        username=username,
        avatar_url=avatar,
        thread=thread
    )


# Parse any inline rolls notation in content
def find_inline_roll(content: str):
    pattern = r'\[\[(.*?)\]\]'
    return re.findall(pattern=pattern, string=content)


async def delete_reaction_message(reaction, user, webhook):
    message = reaction.message
    thread = None
    if hasattr(message.channel, "parent"):
        thread = message.channel

    if thread is None:
        await webhook.delete_message(reaction.message.id)
        return
    await webhook.delete_message(reaction.message.id, thread=thread)


async def edit_reaction_message(reaction, user, webhook):
    pattern = r" \[`🔻`\]\(https://.*?\)$"
    match = re.findall(pattern, reaction.message.content)
    to_be_edited = reaction.message.content.replace(match[0], "")
    await user.send(
        f"Proxy edited: {reaction.message.jump_url}⁠\n" +
        "Editing message:"
    )
    await user.send(to_be_edited)
    await user.send("Please send me the new content of the message here:")

    def check_message(m):
        return m.channel == user.dm_channel and m.author == user

    try:
        msg = await bot.wait_for('message', check=check_message, timeout=300)
    except asyncio.TimeoutError:
        await user.send("Timed out. Message not edited.")
        await reaction.clear()
        return
    else:
        message = reaction.message
        thread = None
        if hasattr(message.channel, "parent"):
            thread = message.channel

        await reaction.clear()
        if thread is None:
            await webhook.edit_message(
                message.id,
                content=msg.content + match[0]
            )
            return
        await webhook.edit_message(
            message.id,
            content=msg.content + match[0],
            thread=thread
        )


async def edit_by_tul_edit(message):
    if not message.content.startswith("tul!edit"):
        return
    await delete_tupper_edit_error(message)
    if message.reference is None:
        return
    if len(message.content.split(" ", 1)) <= 1:
        return
    content = message.content.split(" ", 1)[1]
    reply_message = await message.channel.fetch_message(
        message.reference.message_id)
    if reply_message.webhook_id is None:
        return
    webhook_name = f"{bot.application.name}hook"
    webhook = await bot.fetch_webhook(reply_message.webhook_id)
    if webhook.name != webhook_name:
        return
    await message.delete()
    pattern = r" \[`🔻`\]\(https://.*?\)$"
    match = re.findall(pattern, reply_message.content)
    thread = None
    if hasattr(reply_message.channel, "parent"):
        thread = reply_message.channel

    if thread is None:
        await webhook.edit_message(
            reply_message.id,
            content=content + match[0]
        )
        return
    await webhook.edit_message(
        reply_message.id,
        content=content + match[0],
        thread=thread
    )


async def delete_tupper_edit_error(message):
    error = "That message doesn't seem to be a proxy sent with Tupperbox."
    id = 431544605209788416

    def check(m) -> bool:
        return m.channel.id == message.channel.id and \
            m.author.id == id and \
            m.content == error
    msg = await bot.wait_for('message', check=check, timeout=10)
    await msg.delete()


async def insert_roll_history(
        message: discord.Message,
        d20_roll: d20.RollResult,
        command: str
        ):
    comment = d20_roll.comment
    if comment is not None:
        command = command.replace(comment, "")
        command = command.strip()
    history_repo = RollHistoryRepository()
    history_repo.add_history(
        guild_id=message.guild.id,
        character_name=message.author.name,
        dice_roll=command,
        result=d20_roll.result,
        expression=str(d20_roll.expr),
        crit=d20_roll.crit,
        room_name=message.channel.name
    )


async def insert_modiphius_history(
        message: discord.Message,
        modiphius_result: dict,
        command: str
        ):
    history_repo = RollHistoryRepository()
    history_repo.add_history(
        guild_id=message.guild.id,
        character_name=message.author.name,
        dice_roll=command,
        result=modiphius_result['summary'],
        expression=modiphius_result['expression'],
        crit=0,
        room_name=message.channel.name
    )


async def insert_roll_histories(
        histories_list
        ):
    for history in histories_list:
        if 'modiphius' in history:
            await insert_modiphius_history(
                message=history['message'],
                modiphius_result=history['modiphius'],
                command=history['command']
            )
            continue
        await insert_roll_history(
            message=history['message'],
            d20_roll=history['d20_roll'],
            command=history['command']
        )


bot.run(TOKEN)
