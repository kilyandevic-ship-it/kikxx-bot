import discord
from discord.ext import commands, tasks
import json
import os
import aiohttp
import datetime

# ============================================================
#  CONFIGURATION — MODIFIE CES VALEURS
# ============================================================
DISCORD_TOKEN = "TON_TOKEN_DISCORD_ICI"
TWITCH_CLIENT_ID = "TON_CLIENT_ID_TWITCH"
TWITCH_CLIENT_SECRET = "TON_CLIENT_SECRET_TWITCH"
TWITCH_USERNAME = "TON_PSEUDO_TWITCH"         # ex: kikxx
YOUTUBE_CHANNEL_ID = "TON_ID_CHAINE_YOUTUBE"  # ex: UCxxxxxxxxxxxxxxxx
TIKTOK_USERNAME = "kikxxway"

ANNOUNCE_CHANNEL_ID = 123456789  # ID du salon #live ou #annonces
ROLE_LIVE_ID = 123456789         # ID du rôle à mentionner quand tu go live (optionnel)

XP_FILE = "xp_data.json"
# ============================================================

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

# ── XP System ──────────────────────────────────────────────

def load_xp():
    if os.path.exists(XP_FILE):
        with open(XP_FILE, "r") as f:
            return json.load(f)
    return {}

def save_xp(data):
    with open(XP_FILE, "w") as f:
        json.dump(data, f, indent=2)

def get_level(xp):
    """Paliers de niveau : niveau = racine carrée de xp / 10"""
    return int((xp / 10) ** 0.5)

# ── Twitch Live Detection ───────────────────────────────────

twitch_access_token = None
is_live = False

async def get_twitch_token():
    global twitch_access_token
    url = "https://id.twitch.tv/oauth2/token"
    params = {
        "client_id": TWITCH_CLIENT_ID,
        "client_secret": TWITCH_CLIENT_SECRET,
        "grant_type": "client_credentials"
    }
    async with aiohttp.ClientSession() as session:
        async with session.post(url, params=params) as r:
            data = await r.json()
            twitch_access_token = data.get("access_token")

async def check_twitch_live():
    if not twitch_access_token:
        await get_twitch_token()
    headers = {
        "Client-ID": TWITCH_CLIENT_ID,
        "Authorization": f"Bearer {twitch_access_token}"
    }
    url = f"https://api.twitch.tv/helix/streams?user_login={TWITCH_USERNAME}"
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers) as r:
            data = await r.json()
            streams = data.get("data", [])
            if streams:
                return streams[0]  # infos du stream
            return None

# ── Events ─────────────────────────────────────────────────

@bot.event
async def on_ready():
    print(f"✅ Bot connecté en tant que {bot.user}")
    check_live_loop.start()

@bot.event
async def on_message(message):
    if message.author.bot:
        return

    # XP : +5 à +15 par message
    xp_data = load_xp()
    user_id = str(message.author.id)
    if user_id not in xp_data:
        xp_data[user_id] = {"xp": 0, "level": 0}

    old_level = xp_data[user_id]["level"]
    xp_data[user_id]["xp"] += 10
    new_level = get_level(xp_data[user_id]["xp"])
    xp_data[user_id]["level"] = new_level

    if new_level > old_level:
        await message.channel.send(
            f"🎉 GG {message.author.mention} ! Tu passes au **niveau {new_level}** ! 🔥"
        )

    save_xp(xp_data)
    await bot.process_commands(message)

# ── Tasks ───────────────────────────────────────────────────

@tasks.loop(minutes=3)
async def check_live_loop():
    global is_live
    stream = await check_twitch_live()
    channel = bot.get_channel(ANNOUNCE_CHANNEL_ID)

    if stream and not is_live:
        is_live = True
        title = stream.get("title", "Un stream")
        game = stream.get("game_name", "Unknown")
        viewers = stream.get("viewer_count", 0)
        embed = discord.Embed(
            title=f"🔴 {TWITCH_USERNAME} est EN LIVE !",
            description=f"**{title}**\n🎮 {game} • 👁️ {viewers} viewers",
            color=0x9146FF,
            url=f"https://twitch.tv/{TWITCH_USERNAME}"
        )
        embed.set_footer(text="Viens tchatter 👊")
        role_mention = f"<@&{ROLE_LIVE_ID}>" if ROLE_LIVE_ID else ""
        if channel:
            await channel.send(content=role_mention, embed=embed)

    elif not stream and is_live:
        is_live = False

# ── Commandes ───────────────────────────────────────────────

@bot.command(name="xp")
async def xp_command(ctx, member: discord.Member = None):
    """!xp — Affiche ton XP et ton niveau"""
    target = member or ctx.author
    xp_data = load_xp()
    user_id = str(target.id)
    if user_id not in xp_data:
        await ctx.send(f"{target.mention} n'a pas encore d'XP. Il faut parler !")
        return
    xp = xp_data[user_id]["xp"]
    level = xp_data[user_id]["level"]
    embed = discord.Embed(
        title=f"⭐ Stats de {target.display_name}",
        color=0xFFD700
    )
    embed.add_field(name="Niveau", value=f"**{level}**", inline=True)
    embed.add_field(name="XP Total", value=f"**{xp}**", inline=True)
    await ctx.send(embed=embed)

@bot.command(name="top")
async def top_command(ctx):
    """!top — Classement des membres les plus actifs"""
    xp_data = load_xp()
    sorted_users = sorted(xp_data.items(), key=lambda x: x[1]["xp"], reverse=True)[:10]
    embed = discord.Embed(title="🏆 Top 10 membres actifs", color=0xFFD700)
    medals = ["🥇", "🥈", "🥉"] + ["🔹"] * 7
    lines = []
    for i, (uid, data) in enumerate(sorted_users):
        try:
            user = await bot.fetch_user(int(uid))
            name = user.display_name
        except:
            name = f"User {uid}"
        lines.append(f"{medals[i]} **{name}** — Niveau {data['level']} ({data['xp']} XP)")
    embed.description = "\n".join(lines) if lines else "Personne pour l'instant."
    await ctx.send(embed=embed)

@bot.command(name="live")
async def live_command(ctx):
    """!live — Vérifie si tu es en live Twitch"""
    stream = await check_twitch_live()
    if stream:
        embed = discord.Embed(
            title=f"🔴 {TWITCH_USERNAME} est EN LIVE",
            description=stream.get("title", ""),
            color=0x9146FF,
            url=f"https://twitch.tv/{TWITCH_USERNAME}"
        )
        embed.add_field(name="Jeu", value=stream.get("game_name", "?"), inline=True)
        embed.add_field(name="Viewers", value=stream.get("viewer_count", 0), inline=True)
        await ctx.send(embed=embed)
    else:
        await ctx.send(f"😴 **{TWITCH_USERNAME}** n'est pas en live pour l'instant.")

@bot.command(name="links")
async def links_command(ctx):
    """!links — Affiche tous les liens de la chaîne"""
    embed = discord.Embed(title="🔗 Retrouve Kikxx partout", color=0xFF4500)
    embed.add_field(name="📺 YouTube", value="[Kikxx](https://youtube.com/@kikxxway)", inline=False)
    embed.add_field(name="🎵 TikTok", value=f"[@{TIKTOK_USERNAME}](https://tiktok.com/@{TIKTOK_USERNAME})", inline=False)
    embed.add_field(name="🟣 Twitch", value=f"[{TWITCH_USERNAME}](https://twitch.tv/{TWITCH_USERNAME})", inline=False)
    await ctx.send(embed=embed)

@bot.command(name="roast")
async def roast_command(ctx, member: discord.Member = None):
    """!roast @membre — Balance un roast"""
    import random
    roasts = [
        "{} joue comme si c'était la première fois qu'il voyait un écran.",
        "{} a plus de défaites que de neurones.",
        "{} est tellement mauvais que même les bots le dodge.",
        "{} confond le bouton croix avec le bouton victoire.",
        "{} farm les morts mieux que les minions.",
    ]
    target = member or ctx.author
    roast = random.choice(roasts).format(target.mention)
    await ctx.send(f"🔥 {roast}")

# ── Lancement ───────────────────────────────────────────────

bot.run(DISCORD_TOKEN)
