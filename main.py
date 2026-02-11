import discord
from discord.ext import commands
import aiohttp
import os
import webserver
# ─────────────────────────────────────────────
#  CONFIG — fill these in or use a .env file
# ─────────────────────────────────────────────
DISCORD_TOKEN       = os.environ['discordkey']
ROBLOSECURITY       = os.environ['robloxkey']   # ⚠️ Keep this secret!
PRIVATE_SERVER_LINK = "https://www.roblox.com/games/142823291/Murder-Mystery-2?privateServerLinkCode=30016825251983207114597289690712"    # e.g. https://www.roblox.com/games/...?privateServerLinkCode=...
PLACE_ID            = 142823291        # The Place ID of your game
AUTHORIZED_USER_ID  = 1065774521526800426        # Your Discord user ID (only you can run commands)

# ─────────────────────────────────────────────
#  BOT SETUP
# ─────────────────────────────────────────────
intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

HEADERS = {
    "Cookie": f".ROBLOSECURITY={ROBLOSECURITY}",
    "Content-Type": "application/json",
    "Referer": "https://www.roblox.com",
    "Origin": "https://www.roblox.com",
}

# ─────────────────────────────────────────────
#  HELPER: get CSRF token (required by Roblox)
# ─────────────────────────────────────────────
async def get_csrf_token(session: aiohttp.ClientSession) -> str:
    """Roblox requires an X-CSRF-TOKEN for POST requests."""
    async with session.post(
        "https://auth.roblox.com/v2/logout",
        headers=HEADERS
    ) as resp:
        token = resp.headers.get("x-csrf-token", "")
        return token

# ─────────────────────────────────────────────
#  HELPER: resolve username → user ID
# ─────────────────────────────────────────────
async def get_user_id(session: aiohttp.ClientSession, username: str):
    url = "https://users.roblox.com/v1/usernames/users"
    payload = {"usernames": [username], "excludeBannedUsers": False}
    async with session.post(url, json=payload, headers=HEADERS) as resp:
        data = await resp.json()
        users = data.get("data", [])
        if not users:
            return None
        return users[0]["id"]

# ─────────────────────────────────────────────
#  HELPER: block a user by ID
# ─────────────────────────────────────────────
async def block_user(session: aiohttp.ClientSession, csrf: str, user_id: int) -> bool:
    url = f"https://accountsettings.roblox.com/v1/users/{user_id}/block"
    headers = {**HEADERS, "X-CSRF-TOKEN": csrf}
    async with session.post(url, headers=headers) as resp:
        return resp.status == 200

# ─────────────────────────────────────────────
#  HELPER: shutdown private server
# ─────────────────────────────────────────────
async def shutdown_server(session: aiohttp.ClientSession, csrf: str) -> tuple[bool, str]:
    """
    Uses the Roblox API to close all running game instances for the place.
    This effectively shuts down all servers including private ones.
    """
    url = f"https://www.roblox.com/games/shutdown-all-instances"
    headers = {**HEADERS, "X-CSRF-TOKEN": csrf}
    payload = {"placeId": PLACE_ID}
    async with session.post(url, json=payload, headers=headers) as resp:
        if resp.status == 200:
            return True, "✅ Server shutdown request sent!"
        else:
            text = await resp.text()
            return False, f"❌ Failed (status {resp.status}): {text}"

# ─────────────────────────────────────────────
#  GUARD: only allow the authorized Discord user
# ─────────────────────────────────────────────
def is_authorized(ctx):
    return ctx.author.id == AUTHORIZED_USER_ID

# ─────────────────────────────────────────────
#  COMMAND: !block <roblox_username>
# ─────────────────────────────────────────────
@bot.command(name="block")
async def block_command(ctx, *, username: str = None):
    if not is_authorized(ctx):
        await ctx.send("⛔ You are not authorized to use this command.")
        return
    if not username:
        await ctx.send("Usage: `!block <roblox_username>`")
        return

    await ctx.send(f"🔍 Looking up **{username}**...")

    async with aiohttp.ClientSession() as session:
        csrf = await get_csrf_token(session)
        user_id = await get_user_id(session, username)

        if not user_id:
            await ctx.send(f"❌ Could not find Roblox user **{username}**.")
            return

        success = await block_user(session, csrf, user_id)
        if success:
            await ctx.send(f"✅ Successfully blocked **{username}** (ID: `{user_id}`).")
        else:
            await ctx.send(f"❌ Failed to block **{username}**. Check your cookie/permissions.")

# ─────────────────────────────────────────────
#  COMMAND: !shutdown
# ─────────────────────────────────────────────
@bot.command(name="shutdown")
async def shutdown_command(ctx):
    if not is_authorized(ctx):
        await ctx.send("⛔ You are not authorized to use this command.")
        return
    if PLACE_ID == 0:
        await ctx.send("⚠️ `PLACE_ID` is not set in the config.")
        return

    await ctx.send("⏳ Sending shutdown request to Roblox...")

    async with aiohttp.ClientSession() as session:
        csrf = await get_csrf_token(session)
        success, message = await shutdown_server(session, csrf)
        await ctx.send(message)

# ─────────────────────────────────────────────
#  ON READY
# ─────────────────────────────────────────────
@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user} ({bot.user.id})")
    print("Commands ready: !block <username> | !shutdown")

# ─────────────────────────────────────────────
#  RUN
# ─────────────────────────────────────────────
webserver.keep_alive()
bot.run(DISCORD_TOKEN)
