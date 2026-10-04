import json
import os
from pathlib import Path

import discord
from discord import app_commands
from discord.ext import commands

TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = os.getenv("GUILD_ID")
DATA_FILE = Path("scoobybot_data.json")

if not TOKEN:
    raise RuntimeError("Missing DISCORD_TOKEN environment variable.")
if not GUILD_ID:
    raise RuntimeError("Missing GUILD_ID environment variable.")

GUILD_OBJECT = discord.Object(id=int(GUILD_ID))


def load_data():
    if DATA_FILE.exists():
        try:
            return json.loads(DATA_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {"servers": {}}


data = load_data()


def save_data():
    DATA_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")


def server_data(guild_id: int):
    key = str(guild_id)
    if key not in data["servers"]:
        data["servers"][key] = {
            "channels": {},
            "case": None,
            "case_number": 0,
        }
    return data["servers"][key]


def channel_mention(channel_id):
    return f"<#{channel_id}>" if channel_id else "`not configured`"


def staff_only():
    return app_commands.checks.has_permissions(manage_guild=True)


class ScoobyBot(commands.Bot):
    async def setup_hook(self):
        # Guild-scoped commands appear quickly in your test server.
        self.tree.copy_global_to(guild=GUILD_OBJECT)
        await self.tree.sync(guild=GUILD_OBJECT)


intents = discord.Intents.default()
bot = ScoobyBot(command_prefix="!", intents=intents)


@bot.event
async def on_ready():
    print(f"ScoobyBot is online as {bot.user} (ID: {bot.user.id})")


mystery = app_commands.Group(name="mystery", description="Manage Mystery Inc. weekly cases")


@mystery.command(name="setup", description="Connect ScoobyBot to your mystery channels")
@staff_only()
@app_commands.describe(
    weekly_mystery="Announcement channel for each new weekly mystery",
    case_files="Channel containing the full case file",
    clue_hunting="Channel for clues and evidence",
    theory_room="Channel for discussing theories",
    who_done_it="Channel for final accusations",
    villain_reveals="Channel for the official reveal",
)
async def mystery_setup(
    interaction: discord.Interaction,
    weekly_mystery: discord.TextChannel,
    case_files: discord.TextChannel,
    clue_hunting: discord.TextChannel,
    theory_room: discord.TextChannel,
    who_done_it: discord.TextChannel,
    villain_reveals: discord.TextChannel,
):
    if interaction.guild is None:
        await interaction.response.send_message("Run this command inside your server.", ephemeral=True)
        return

    config = server_data(interaction.guild.id)
    config["channels"] = {
        "weekly_mystery": weekly_mystery.id,
        "case_files": case_files.id,
        "clue_hunting": clue_hunting.id,
        "theory_room": theory_room.id,
        "who_done_it": who_done_it.id,
        "villain_reveals": villain_reveals.id,
    }
    save_data()

    await interaction.response.send_message(
        "🐾 **Mystery Inc. channels connected!**\n"
        f"🔎 Weekly Mystery: {weekly_mystery.mention}\n"
        f"📁 Case Files: {case_files.mention}\n"
        f"🔦 Clue Hunting: {clue_hunting.mention}\n"
        f"💭 Theory Room: {theory_room.mention}\n"
        f"🕵️ Who Done It: {who_done_it.mention}\n"
        f"🎭 Villain Reveals: {villain_reveals.mention}",
        ephemeral=True,
    )


@mystery.command(name="start", description="Open a new weekly mystery case")
@staff_only()
@app_commands.describe(title="Case title", story="Short introduction to the mystery")
async def mystery_start(interaction: discord.Interaction, title: str, story: str):
    if interaction.guild is None:
        await interaction.response.send_message("Run this command inside your server.", ephemeral=True)
        return

    config = server_data(interaction.guild.id)
    channels = config.get("channels", {})
    weekly_id = channels.get("weekly_mystery")
    case_id = channels.get("case_files")

    if not weekly_id or not case_id:
        await interaction.response.send_message(
            "Ruh-roh! Channels aren't configured yet. Ask a server admin to run `/mystery setup` first.",
            ephemeral=True,
        )
        return

    if config.get("case") and config["case"].get("status") == "open":
        await interaction.response.send_message(
            "There's already an open case! Close or reveal it before starting another.",
            ephemeral=True,
        )
        return

    weekly_channel = interaction.guild.get_channel(weekly_id)
    case_channel = interaction.guild.get_channel(case_id)
    if not isinstance(weekly_channel, discord.TextChannel) or not isinstance(case_channel, discord.TextChannel):
        await interaction.response.send_message(
            "I can't find one of the configured channels. Run `/mystery setup` again.",
            ephemeral=True,
        )
        return

    config["case_number"] = int(config.get("case_number", 0)) + 1
    case_number = config["case_number"]
    config["case"] = {
        "number": case_number,
        "title": title,
        "story": story,
        "status": "open",
        "clues": [],
        "solution": None,
    }
    save_data()

    embed = discord.Embed(
        title=f"📁 CASE FILE #{case_number:03d}: {title}",
        description=story,
        color=discord.Color.dark_blue(),
    )
    embed.add_field(
        name="🔎 Your mission",
        value=(
            f"Read the full case in {case_channel.mention}.\n"
            f"Search for evidence in {channel_mention(channels.get('clue_hunting'))}.\n"
            f"Discuss theories in {channel_mention(channels.get('theory_room'))}.\n"
            f"Submit your final accusation in {channel_mention(channels.get('who_done_it'))}."
        ),
        inline=False,
    )
    embed.set_footer(text="CASE STATUS: OPEN • No spoilers until the official reveal!")

    await case_channel.send(embed=embed)
    await weekly_channel.send(
        f"🐾🔎 **MYSTERY INC. CASE FILE #{case_number:03d} IS OPEN!**\n"
        f"**{title}**\n{story}\n\n"
        f"📁 **NEXT STOP:** Head to {case_channel.mention} to read the full case, meet the suspects, and inspect the evidence!\n"
        "Like, let's solve this thing, gang! 🐶🍪"
    )
    await interaction.response.send_message(f"Case #{case_number:03d} opened in {weekly_channel.mention}.", ephemeral=True)


@mystery.command(name="clue", description="Release a new clue for the current case")
@staff_only()
@app_commands.describe(clue="The clue members should investigate")
async def mystery_clue(interaction: discord.Interaction, clue: str):
    if interaction.guild is None:
        await interaction.response.send_message("Run this command inside your server.", ephemeral=True)
        return

    config = server_data(interaction.guild.id)
    case = config.get("case")
    clue_channel_id = config.get("channels", {}).get("clue_hunting")
    if not case or case.get("status") != "open" or not clue_channel_id:
        await interaction.response.send_message("No open case, or the clue channel isn't configured.", ephemeral=True)
        return

    channel = interaction.guild.get_channel(clue_channel_id)
    if not isinstance(channel, discord.TextChannel):
        await interaction.response.send_message("I can't find the clue channel. Run `/mystery setup` again.", ephemeral=True)
        return

    case.setdefault("clues", []).append(clue)
    save_data()
    await channel.send(
        f"🔦 **NEW EVIDENCE — CASE #{case['number']:03d}**\n{clue}\n\n"
        f"Share your ideas in {channel_mention(config['channels'].get('theory_room'))}."
    )
    await interaction.response.send_message("Clue released. The detectives are on it!", ephemeral=True)


@mystery.command(name="close", description="Close submissions for the current case")
@staff_only()
async def mystery_close(interaction: discord.Interaction):
    if interaction.guild is None:
        await interaction.response.send_message("Run this command inside your server.", ephemeral=True)
        return

    config = server_data(interaction.guild.id)
    case = config.get("case")
    if not case or case.get("status") != "open":
        await interaction.response.send_message("There isn't an open case to close.", ephemeral=True)
        return

    case["status"] = "closed"
    save_data()
    channels = config.get("channels", {})
    for key in ("weekly_mystery", "who_done_it"):
        channel = interaction.guild.get_channel(channels.get(key, 0))
        if isinstance(channel, discord.TextChannel):
            await channel.send(
                f"🛑 **CASE #{case['number']:03d} — SUBMISSIONS CLOSED**\n"
                "No more final accusations, detectives! The official unmasking is coming soon. 🎭"
            )
    await interaction.response.send_message("Case closed to new submissions. Use `/mystery reveal` for the official solution.", ephemeral=True)


@mystery.command(name="reveal", description="Publish the culprit and solution, closing the case")
@staff_only()
@app_commands.describe(culprit="The culprit's name", explanation="How the mystery was solved")
async def mystery_reveal(interaction: discord.Interaction, culprit: str, explanation: str):
    if interaction.guild is None:
        await interaction.response.send_message("Run this command inside your server.", ephemeral=True)
        return

    config = server_data(interaction.guild.id)
    case = config.get("case")
    reveal_id = config.get("channels", {}).get("villain_reveals")
    if not case or case.get("status") not in ("open", "closed") or not reveal_id:
        await interaction.response.send_message("No case is ready to reveal, or the reveal channel isn't configured.", ephemeral=True)
        return

    channel = interaction.guild.get_channel(reveal_id)
    if not isinstance(channel, discord.TextChannel):
        await interaction.response.send_message("I can't find the reveal channel. Run `/mystery setup` again.", ephemeral=True)
        return

    case["status"] = "revealed"
    case["solution"] = {"culprit": culprit, "explanation": explanation}
    save_data()

    embed = discord.Embed(
        title=f"🎭 CASE #{case['number']:03d}: THE VILLAIN IS UNMASKED!",
        description=f"**The culprit was... {culprit}!**\n\n{explanation}",
        color=discord.Color.gold(),
    )
    embed.add_field(name="Case status", value="✅ CLOSED", inline=True)
    embed.set_footer(text="And we'd have gotten away with it, too, if it weren't for you meddling detectives!")
    await channel.send(embed=embed)
    await interaction.response.send_message(f"Reveal posted in {channel.mention}. Case closed!", ephemeral=True)


@mystery.command(name="status", description="Check the current mystery's status")
async def mystery_status(interaction: discord.Interaction):
    if interaction.guild is None:
        await interaction.response.send_message("Run this command inside your server.", ephemeral=True)
        return
    case = server_data(interaction.guild.id).get("case")
    if not case:
        await interaction.response.send_message("No cases have been started yet. Ask a moderator to use `/mystery start`.")
        return
    await interaction.response.send_message(
        f"🔎 **CASE #{case['number']:03d}: {case['title']}**\n"
        f"Status: **{case['status'].upper()}**\n"
        f"Clues released: **{len(case.get('clues', []))}**"
    )


bot.tree.add_command(mystery)
bot.run(TOKEN)
