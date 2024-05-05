import discord
import d20
import re
import os
from discord.ext import commands
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

intents = discord.Intents.all()

bot = commands.Bot(command_prefix=[";;"], intents=intents)


@bot.event
async def on_ready():
    print("We have logged in as {0.user}".format(bot))


@bot.event
async def on_reaction_add(reaction, user):
    if user.bot:
        return
    if reaction.message.webhook_id is None:
        return
    if reaction.emoji != "❌":
        return
    webhook_name = f"{bot.application.name}hook"
    webhook = await bot.fetch_webhook(reaction.message.webhook_id)
    if webhook.name != webhook_name:
        return
    message = reaction.message
    thread = None
    if hasattr(message.channel, "parent"):
        thread = message.channel

    if thread is None:
        await webhook.delete_message(reaction.message.id)
        return
    await webhook.delete_message(reaction.message.id, thread=thread)


@bot.event
async def on_message(message):
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
    channel = message.channel

    thread = None
    dump_channel = await bot.fetch_channel(939933100752924693)
    if hasattr(message.channel, "parent"):
        channel = message.channel.parent
        thread = message.channel
        dump_channel = channel

    webhook = await create_webhook_by_channel(channel, bot.application.name)

    result_texts = []
    for inline_roll in inline_rolls:
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
        inline_replacement = f"`( {result.total}{crit}{comment} )`"
        content = content.replace(f"[[{inline_roll}]]", inline_replacement, 1)
    full_result = '\n'.join(result_texts)

    dump_message = await dump_channel.send(
        f"@{display_name}:" + "\n" +
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


bot.run(TOKEN)
