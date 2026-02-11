import discord
from discord.ext import commands
import aiohttp
import os
import webserver

# ─────────────────────────────────────────────
#  CONFIG
# ─────────────────────────────────────────────
DISCORD_TOKEN        = os.environ["discordkey"]
ROBLOSECURITY        = os.environ["robloxkey"]  # ⚠️ Keep this secret!

AUTHORIZED_ROLE_ID   = 1470992691037737181

PLACE_ID             = 142823291
PRIVATE_SERVER_ID  = "281054734"

# ─────────────────────────────────────────────
#  BOT SETUP
# ─────────────────────────────────────────────
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

HEADERS = {
    "Cookie": f".ROBLOSECURITY={ROBLOSECURITY}; RBXEventTrackerV2=CreateDate=02/10/2026 19:26:42&rbxid=193759500&browserid=1770773163207002",
    "Content-Type": "application/json",
    "Referer": "https://www.roblox.com",
    "Origin": "https://www.roblox.com",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
}

# ─────────────────────────────────────────────
#  EMBED HELPERS
# ─────────────────────────────────────────────
def embed_info(title, description):
    return discord.Embed(title=title, description=description, color=0x5865F2)

def embed_success(title, description):
    return discord.Embed(title=title, description=description, color=0x57F287)

def embed_error(title, description):
    return discord.Embed(title=title, description=description, color=0xED4245)

def embed_warning(title, description):
    return discord.Embed(title=title, description=description, color=0xFEE75C)

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
        data = await resp.json()
        users = data.get("data", [])
        if not users:
            return None
        return users[0]["id"]

# ─────────────────────────────────────────────
#  HELPER: get avatar thumbnail URL
# ─────────────────────────────────────────────
async def get_avatar_url(session: aiohttp.ClientSession, user_id: int) -> str | None:
    url = (
        f"https://thumbnails.roblox.com/v1/users/avatar-headshot"
        f"?userIds={user_id}&size=420x420&format=Png&isCircular=false"
    )
    async with session.get(url, headers=HEADERS) as resp:
        if resp.status != 200:
            return None
        data = await resp.json()
        items = data.get("data", [])
        if not items:
            return None
        return items[0].get("imageUrl")

# ─────────────────────────────────────────────
#  HELPER: block a user by ID
# ─────────────────────────────────────────────
async def block_user(session: aiohttp.ClientSession, csrf: str, user_id: int) -> tuple[bool, str]:
    headers = {**HEADERS, "X-CSRF-TOKEN": csrf}
    url = f"https://apis.roblox.com/user-blocking-api/v1/users/{user_id}/block-user"
    async with session.post(url, headers=headers) as resp:
        text = await resp.text()
        print(f"[BLOCK] Status: {resp.status} | Response: {text}")
        return resp.status in (200, 204), text

# ─────────────────────────────────────────────
#  HELPER: unblock a user by ID
# ─────────────────────────────────────────────
async def unblock_user(session: aiohttp.ClientSession, csrf: str, user_id: int) -> tuple[bool, str]:
    headers = {**HEADERS, "X-CSRF-TOKEN": csrf}
    url = f"https://apis.roblox.com/user-blocking-api/v1/users/{user_id}/unblock-user"
    async with session.post(url, headers=headers) as resp:
        text = await resp.text()
        print(f"[UNBLOCK] Status: {resp.status} | Response: {text}")
        return resp.status in (200, 204), text

# ─────────────────────────────────────────────
#  HELPER: get private server ID from link code
# ─────────────────────────────────────────────
async def get_private_server_id(session: aiohttp.ClientSession) -> tuple[str | None, str]:
    return str(PRIVATE_SERVER_ID), ""

# ─────────────────────────────────────────────
#  HELPER: shutdown private server by ID
# ─────────────────────────────────────────────
async def shutdown_private_server(session: aiohttp.ClientSession, csrf: str, server_id: str) -> tuple[bool, str]:
    url = f"https://games.roblox.com/v1/vip-servers/{server_id}"
    headers = {**HEADERS, "X-CSRF-TOKEN": csrf}

    # Step 1: Deactivate (kicks everyone)
    payload = {"active": False}
    async with session.patch(url, json=payload, headers=headers) as resp:
        text = await resp.text()
        print(f"[SHUTDOWN] Deactivate Status: {resp.status} | Response: {text}")
        if resp.status not in (200, 204):
            return False, f"Failed to deactivate: {text}"

    # Step 2: Reactivate immediately
    payload = {"active": True}
    async with session.patch(url, json=payload, headers=headers) as resp:
        text = await resp.text()
        print(f"[SHUTDOWN] Reactivate Status: {resp.status} | Response: {text}")
        if resp.status in (200, 204):
            return True, ""
        else:
            return False, f"Failed to reactivate: {text}"

# ─────────────────────────────────────────────
#  GUARD: only allow the authorized Discord user
# ─────────────────────────────────────────────
def is_authorized(ctx):
    # Check if user has a specific role (by role ID)
    role = discord.utils.get(ctx.author.roles, id=AUTHORIZED_ROLE_ID)
    return role is not None

# ─────────────────────────────────────────────
#  UNBAN BUTTON VIEW
# ─────────────────────────────────────────────
class UnbanView(discord.ui.View):
    def __init__(self, user_id: int, username: str, avatar_url: str | None):
        super().__init__(timeout=300)  # Button expires after 5 minutes
        self.user_id = user_id
        self.username = username
        self.avatar_url = avatar_url

    @discord.ui.button(label="Unban", style=discord.ButtonStyle.green, emoji="🔓")
    async def unban_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Check if user has the authorized role
        role = discord.utils.get(interaction.user.roles, id=AUTHORIZED_ROLE_ID)
        if role is None:
            await interaction.response.send_message(
                embed=embed_error("⛔ Unauthorized", "You are not authorized to use this button."),
                ephemeral=True
            )
            return
        await interaction.response.defer()

        async with aiohttp.ClientSession() as session:
            csrf = await get_csrf_token(session)
            success, response = await unblock_user(session, csrf, self.user_id)

        if success:
            e = embed_success("🔓 User Unbanned", f"**{self.username}** has been unbanned.")
            e.add_field(name="Roblox ID", value=f"`{self.user_id}`")
            if self.avatar_url:
                e.set_thumbnail(url=self.avatar_url)
            # Disable the button after use
            button.disabled = True
            button.label = "Unbanned"
            await interaction.message.edit(view=self)
            await interaction.followup.send(embed=e)
        else:
            await interaction.followup.send(
                embed=embed_error("❌ Unban Failed", f"Could not unban **{self.username}**.\n```{response}```")
            )

# ─────────────────────────────────────────────
#  COMMAND: !ban <roblox_username>
#  Permanently blocks the user
# ─────────────────────────────────────────────
@bot.command(name="ban")
async def ban_command(ctx, *, username: str = None):
    if not is_authorized(ctx):
        await ctx.send(embed=embed_error("⛔ Unauthorized", "You are not authorized to use this command."))
        return
    if not username:
        await ctx.send(embed=embed_warning("Usage", "`!ban <roblox_username>`"))
        return

    await ctx.send(embed=embed_info("🔍 Looking up user...", f"Searching for **{username}**"))

    async with aiohttp.ClientSession() as session:
        csrf = await get_csrf_token(session)
        user_id = await get_user_id(session, username)
        if not user_id:
            await ctx.send(embed=embed_error("❌ User Not Found", f"Could not find Roblox user **{username}**."))
            return

        avatar_url = await get_avatar_url(session, user_id)

        await ctx.send(embed=embed_info("⏳ Banning...", f"Blocking **{username}** (ID: `{user_id}`)"))
        success, response = await block_user(session, csrf, user_id)
        if success:
            e = embed_success("🔨 User Banned", f"**{username}** has been permanently banned.")
            e.add_field(name="Roblox ID", value=f"`{user_id}`")
            e.add_field(name="Action", value="Blocked")
            if avatar_url:
                e.set_thumbnail(url=avatar_url)
            view = UnbanView(user_id, username, avatar_url)
            await ctx.send(embed=e, view=view)
        else:
            await ctx.send(embed=embed_error("❌ Ban Failed", f"Could not ban **{username}**.\n```{response}```"))

# ─────────────────────────────────────────────
#  COMMAND: !kick <roblox_username>
#  Blocks then immediately unblocks
# ─────────────────────────────────────────────
@bot.command(name="kick")
async def kick_command(ctx, *, username: str = None):
    if not is_authorized(ctx):
        await ctx.send(embed=embed_error("⛔ Unauthorized", "You are not authorized to use this command."))
        return
    if not username:
        await ctx.send(embed=embed_warning("Usage", "`!kick <roblox_username>`"))
        return

    await ctx.send(embed=embed_info("🔍 Looking up user...", f"Searching for **{username}**"))

    async with aiohttp.ClientSession() as session:
        csrf = await get_csrf_token(session)
        user_id = await get_user_id(session, username)
        if not user_id:
            await ctx.send(embed=embed_error("❌ User Not Found", f"Could not find Roblox user **{username}**."))
            return

        avatar_url = await get_avatar_url(session, user_id)

        await ctx.send(embed=embed_info("⏳ Kicking...", f"Removing **{username}** from the server"))
        block_ok, block_resp = await block_user(session, csrf, user_id)
        if not block_ok:
            await ctx.send(embed=embed_error("❌ Kick Failed", f"Could not kick **{username}**.\n```{block_resp}```"))
            return

        unblock_ok, unblock_resp = await unblock_user(session, csrf, user_id)
        if unblock_ok:
            e = embed_success("👢 User Kicked", f"**{username}** has been kicked from the server.")
            e.add_field(name="Roblox ID", value=f"`{user_id}`")
            e.add_field(name="Action", value="Blocked + Unblocked")
            if avatar_url:
                e.set_thumbnail(url=avatar_url)
            await ctx.send(embed=e)
        else:
            await ctx.send(embed=embed_warning("⚠️ Partial Success", f"**{username}** was blocked but could not be unblocked.\n```{unblock_resp}```"))

# ─────────────────────────────────────────────
#  COMMAND: !shutdown
# ─────────────────────────────────────────────
@bot.command(name="shutdown")
async def shutdown_command(ctx):
    if not is_authorized(ctx):
        await ctx.send(embed=embed_error("⛔ Unauthorized", "You are not authorized to use this command."))
        return

    await ctx.send(embed=embed_info("🔍 Looking up server...", "Finding your private server"))

    async with aiohttp.ClientSession() as session:
        csrf = await get_csrf_token(session)
        server_id, error = await get_private_server_id(session)
        if not server_id:
            await ctx.send(embed=embed_error("❌ Server Not Found", f"```{error}```"))
            return

        await ctx.send(embed=embed_info("⏳ Shutting down...", f"Sending shutdown request for server `{server_id}`"))
        success, message = await shutdown_private_server(session, csrf, server_id)
        if success:
            e = embed_success("🔴 Server Shut Down", "The private server has been shut down successfully.")
            e.add_field(name="Server ID", value=f"`{server_id}`")
            await ctx.send(embed=e)
        else:
            await ctx.send(embed=embed_error("❌ Shutdown Failed", f"```{message}```"))

# ─────────────────────────────────────────────
#  ERROR HANDLER
# ─────────────────────────────────────────────
@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        return
    await ctx.send(embed=embed_error("⚠️ Error", f"```{error}```"))
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
    print("Commands ready: !ban | !kick | !shutdown")

# ─────────────────────────────────────────────
#  RUN
# ─────────────────────────────────────────────
webserver.keep_alive()
bot.run(DISCORD_TOKEN)
