import discord
from discord.ext import commands
import aiohttp
import webserver

# ─────────────────────────────────────────────
#  CONFIG
# ─────────────────────────────────────────────
DISCORD_TOKEN        = os.environ["discordkey"]
ROBLOSECURITY        = os.environ["robloxkey"] # ⚠️ Keep this secret!
AUTHORIZED_USER_ID   = 1065774521526800426       # Your Discord user ID

PLACE_ID             = 142823291
PRIVATE_SERVER_CODE  = "30016825251983207114597289690712"

# ─────────────────────────────────────────────
#  BOT SETUP
# ─────────────────────────────────────────────
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

HEADERS = {
    "Cookie": f".ROBLOSECURITY={ROBLOSECURITY}",
    "Content-Type": "application/json",
    "Referer": "https://www.roblox.com",
    "Origin": "https://www.roblox.com",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
}

# ─────────────────────────────────────────────
#  HELPER: get CSRF token
# ─────────────────────────────────────────────
async def get_csrf_token(session: aiohttp.ClientSession) -> str:
    endpoints = [
        "https://auth.roblox.com/v2/logout",
        "https://accountsettings.roblox.com/v1/email",
        "https://friends.roblox.com/v1/users/1/request-friendship",
    ]
    for url in endpoints:
        try:
            async with session.post(url, headers=HEADERS) as resp:
                token = resp.headers.get("x-csrf-token", "")
                if token:
                    print(f"[CSRF] Got token from {url}")
                    return token
        except Exception as e:
            print(f"[CSRF] Failed on {url}: {e}")
    print("[CSRF] WARNING: Could not retrieve CSRF token!")
    return ""

# ─────────────────────────────────────────────
#  HELPER: resolve username → user ID
# ─────────────────────────────────────────────
async def get_user_id(session: aiohttp.ClientSession, username: str):
    url = "https://users.roblox.com/v1/usernames/users"
    payload = {"usernames": [username], "excludeBannedUsers": False}
    async with session.post(url, json=payload, headers=HEADERS) as resp:
        print(f"[USER LOOKUP] Status: {resp.status}")
        data = await resp.json()
        print(f"[USER LOOKUP] Response: {data}")
        users = data.get("data", [])
        if not users:
            return None
        return users[0]["id"]

# ─────────────────────────────────────────────
#  HELPER: block a user by ID
# ─────────────────────────────────────────────
async def block_user(session: aiohttp.ClientSession, csrf: str, user_id: int) -> tuple[bool, str]:
    url = f"https://accountsettings.roblox.com/v1/users/{user_id}/block"
    headers = {**HEADERS, "X-CSRF-TOKEN": csrf}
    async with session.post(url, headers=headers) as resp:
        text = await resp.text()
        print(f"[BLOCK] Status: {resp.status} | Response: {text}")
        return resp.status == 200, text

# ─────────────────────────────────────────────
#  HELPER: get private server ID from link code
# ─────────────────────────────────────────────
async def get_private_server_id(session: aiohttp.ClientSession) -> tuple[str | None, str]:
    """Resolves the privateServerLinkCode to an actual server ID."""
    url = f"https://games.roblox.com/v1/games/{PLACE_ID}/private-servers?privateServerLinkCode={PRIVATE_SERVER_CODE}"
    async with session.get(url, headers=HEADERS) as resp:
        text = await resp.text()
        print(f"[PS LOOKUP] Status: {resp.status} | Response: {text}")
        if resp.status != 200:
            return None, f"Status {resp.status}: {text}"
        data = await resp.json() if resp.content_type == "application/json" else {}
        # The response contains the private server details
        server_id = data.get("id") or data.get("privateServerId")
        if not server_id:
            return None, f"Could not find server ID in response: {text}"
        return str(server_id), ""

# ─────────────────────────────────────────────
#  HELPER: shutdown private server by ID
# ─────────────────────────────────────────────
async def shutdown_private_server(session: aiohttp.ClientSession, csrf: str, server_id: str) -> tuple[bool, str]:
    url = f"https://games.roblox.com/v1/private-servers/{server_id}"
    headers = {**HEADERS, "X-CSRF-TOKEN": csrf}
    # PATCH to set active=false shuts it down without permanently deleting it
    payload = {"active": False}
    async with session.patch(url, json=payload, headers=headers) as resp:
        text = await resp.text()
        print(f"[SHUTDOWN] Status: {resp.status} | Response: {text}")
        if resp.status == 200:
            return True, "✅ Private server has been shut down!"
        else:
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
        print(f"[BLOCK CMD] CSRF token: '{csrf}'")

        user_id = await get_user_id(session, username)
        if not user_id:
            await ctx.send(f"❌ Could not find Roblox user **{username}**.")
            return

        success, response = await block_user(session, csrf, user_id)
        if success:
            await ctx.send(f"✅ Successfully blocked **{username}** (ID: `{user_id}`).")
        else:
            await ctx.send(f"❌ Failed to block **{username}**. Response: `{response}`")

# ─────────────────────────────────────────────
#  COMMAND: !shutdown
# ─────────────────────────────────────────────
@bot.command(name="shutdown")
async def shutdown_command(ctx):
    if not is_authorized(ctx):
        await ctx.send("⛔ You are not authorized to use this command.")
        return

    await ctx.send("🔍 Looking up private server...")

    async with aiohttp.ClientSession() as session:
        csrf = await get_csrf_token(session)

        server_id, error = await get_private_server_id(session)
        if not server_id:
            await ctx.send(f"❌ Could not find private server. `{error}`")
            return

        await ctx.send(f"⏳ Shutting down server `{server_id}`...")
        success, message = await shutdown_private_server(session, csrf, server_id)
        await ctx.send(message)

# ─────────────────────────────────────────────
#  ERROR HANDLER
# ─────────────────────────────────────────────
@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        return
    await ctx.send(f"⚠️ Error: `{error}`")
    raise error

# ─────────────────────────────────────────────
#  MESSAGE HANDLER
# ─────────────────────────────────────────────
@bot.event
async def on_message(message):
    print(f"[MESSAGE] {message.author}: {message.content}")
    await bot.process_commands(message)

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
