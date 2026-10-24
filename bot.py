import os
import asyncio
import logging
from collections import deque
from urllib.parse import urlparse

import discord
from discord import app_commands
from discord.ext import commands
import yt_dlp
from ddgs import DDGS

TOKEN = os.getenv("DISCORD_TOKEN")
SPOTIFY_CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID", "")
SPOTIFY_CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET", "")

logging.basicConfig(level=logging.INFO)
intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

YDL_OPTIONS = {
    "format": "bestaudio/best",
    "noplaylist": True,
    "quiet": True,
    "no_warnings": True,
    "default_search": "ytsearch",
    "source_address": "0.0.0.0",
}
FFMPEG_OPTIONS = {
    "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
    "options": "-vn",
}
queues = {}  # guild_id -> deque of (title, webpage_url)
spotify = None

def is_spotify_url(value: str) -> bool:
    try:
        return urlparse(value).hostname in {"open.spotify.com", "spotify.com", "www.spotify.com"}
    except Exception:
        return False

async def resolve_spotify(value: str):
    """Return a searchable title for a Spotify track, when Spotify API credentials are set."""
    global spotify
    if not (SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET):
        raise RuntimeError("Spotify links need Spotify Developer API credentials. Add SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET in your host's environment variables.")
    try:
        import spotipy
        from spotipy.oauth2 import SpotifyClientCredentials
        if spotify is None:
            spotify = spotipy.Spotify(auth_manager=SpotifyClientCredentials(
                client_id=SPOTIFY_CLIENT_ID, client_secret=SPOTIFY_CLIENT_SECRET))
        parsed = urlparse(value)
        parts = parsed.path.strip("/").split("/")
        if len(parts) < 2 or parts[0] != "track":
            raise RuntimeError("For now, Spotify support is for individual track links (not playlists/albums).")
        track = await asyncio.to_thread(spotify.track, parts[1])
        artists = ", ".join(a["name"] for a in track.get("artists", []))
        return f'{track["name"]} {artists}'
    except RuntimeError:
        raise
    except Exception as exc:
        raise RuntimeError(f"Could not read that Spotify track: {exc}") from exc

async def get_track(query: str):
    if is_spotify_url(query):
        query = await resolve_spotify(query)
    def extract():
        with yt_dlp.YoutubeDL(YDL_OPTIONS) as ydl:
            info = ydl.extract_info(query, download=False)
            if "entries" in info:
                info = next((entry for entry in info["entries"] if entry), None)
            if not info:
                raise RuntimeError("No playable result found.")
            return {"title": info.get("title", "Unknown title"),
                    "url": info.get("webpage_url") or info.get("original_url") or query}
    return await asyncio.to_thread(extract)

async def play_next(guild: discord.Guild):
    queue = queues.get(guild.id, deque())
    if not queue:
        return
    voice = guild.voice_client
    if not voice or not voice.is_connected():
        return
    title, url = queue.popleft()
    try:
        def get_stream():
            with yt_dlp.YoutubeDL(YDL_OPTIONS) as ydl:
                info = ydl.extract_info(url, download=False)
                if "entries" in info:
                    info = next((entry for entry in info["entries"] if entry), None)
                if not info:
                    raise RuntimeError("Could not load the audio stream.")
                return info["url"]
        stream_url = await asyncio.to_thread(get_stream)
        source = discord.FFmpegPCMAudio(stream_url, **FFMPEG_OPTIONS)
        voice.play(source, after=lambda error: asyncio.run_coroutine_threadsafe(
            play_next(guild), bot.loop))
        bot.loop.create_task(send_now_playing(guild, title, url))
    except Exception:
        logging.exception("Playback error")
        await play_next(guild)

async def send_now_playing(guild, title, url):
    channel_id = getattr(guild, "system_channel", None)
    if channel_id:
        try:
            await channel_id.send(f"🎶 Now playing: **{discord.utils.escape_markdown(title)}**\n{url}")
        except discord.HTTPException:
            pass

async def ensure_voice(interaction: discord.Interaction):
    if not interaction.guild:
        raise app_commands.AppCommandError("Use this command in a server.")
    if not interaction.user.voice or not interaction.user.voice.channel:
        raise app_commands.AppCommandError("Join a voice channel first.")
    voice = interaction.guild.voice_client
    if voice is None:
        voice = await interaction.user.voice.channel.connect()
    elif voice.channel != interaction.user.voice.channel:
        await voice.move_to(interaction.user.voice.channel)
    return voice

@bot.event
async def on_ready():
    try:
        synced = await bot.tree.sync()
        logging.info("Logged in as %s; synced %s slash commands", bot.user, len(synced))
    except Exception:
        logging.exception("Slash-command sync failed")
    logging.info("Bot ready.")

@bot.tree.command(name="help", description="Show commands for search and music")
async def help_command(interaction: discord.Interaction):
    embed = discord.Embed(title="Search + Music Bot", color=discord.Color.blurple())
    embed.description = (
        "**Web**\n`/google query` — search the web\n\n"
        "**Music** (join a voice channel first)\n"
        "`/play query_or_link` — play or queue a track\n"
        "`/skip` — skip current track\n"
        "`/pause` — pause playback\n"
        "`/resume` — resume playback\n"
        "`/queue` — show queued tracks\n"
        "`/stop` — stop, clear queue, and disconnect\n\n"
        "YouTube searches and links are supported. Spotify individual track links can be resolved when Spotify API credentials are configured."
    )
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="google", description="Search the web and return clickable results")
@app_commands.describe(query="What do you want to search for?")
async def google(interaction: discord.Interaction, query: str):
    await interaction.response.defer(thinking=True)
    try:
        results = await asyncio.to_thread(lambda: list(DDGS().text(query, max_results=5)))
        if not results:
            await interaction.followup.send("No results found. Try a different search.")
            return
        embed = discord.Embed(title=f"Web search: {query[:200]}", color=discord.Color.blurple())
        for item in results[:5]:
            title = item.get("title") or "Untitled result"
            href = item.get("href") or item.get("url") or ""
            body = (item.get("body") or "No description available.")[:300]
            if href:
                embed.add_field(name=f"🔗 {title[:250]}", value=f"{body}\n{href}", inline=False)
        await interaction.followup.send(embed=embed)
    except Exception:
        logging.exception("Search failed")
        await interaction.followup.send("Search failed right now. Please try again in a moment.")

@bot.tree.command(name="play", description="Play or queue a YouTube track or supported Spotify track link")
@app_commands.describe(query="Song name, YouTube URL, or Spotify track URL")
async def play(interaction: discord.Interaction, query: str):
    await interaction.response.defer(thinking=True)
    try:
        await ensure_voice(interaction)
        track = await get_track(query)
        queue = queues.setdefault(interaction.guild_id, deque())
        voice = interaction.guild.voice_client
        if voice and voice.is_playing():
            queue.append((track["title"], track["url"]))
            await interaction.followup.send(f"➕ Added to queue: **{discord.utils.escape_markdown(track['title'])}**")
        else:
            queue.appendleft((track["title"], track["url"]))
            await interaction.followup.send(f"▶️ Starting: **{discord.utils.escape_markdown(track['title'])}**")
            await play_next(interaction.guild)
    except Exception as exc:
        await interaction.followup.send(f"Couldn't play that: {exc}")

@bot.tree.command(name="skip", description="Skip the current song")
async def skip(interaction: discord.Interaction):
    voice = interaction.guild.voice_client if interaction.guild else None
    if not voice or not voice.is_playing():
        await interaction.response.send_message("Nothing is playing right now.", ephemeral=True)
        return
    voice.stop()
    await interaction.response.send_message("⏭️ Skipped.")

@bot.tree.command(name="pause", description="Pause the current song")
async def pause(interaction: discord.Interaction):
    voice = interaction.guild.voice_client if interaction.guild else None
    if not voice or not voice.is_playing():
        await interaction.response.send_message("Nothing is playing right now.", ephemeral=True)
        return
    voice.pause()
    await interaction.response.send_message("⏸️ Paused.")

@bot.tree.command(name="resume", description="Resume paused music")
async def resume(interaction: discord.Interaction):
    voice = interaction.guild.voice_client if interaction.guild else None
    if not voice or not voice.is_paused():
        await interaction.response.send_message("Nothing is paused right now.", ephemeral=True)
        return
    voice.resume()
    await interaction.response.send_message("▶️ Resumed.")

@bot.tree.command(name="queue", description="Show the upcoming music queue")
async def show_queue(interaction: discord.Interaction):
    queue = queues.get(interaction.guild_id, deque())
    if not queue:
        await interaction.response.send_message("The queue is empty.")
        return
    lines = [f"**{i}.** {discord.utils.escape_markdown(title)} — {url}" for i, (title, url) in enumerate(list(queue)[:10], 1)]
    await interaction.response.send_message("🎶 **Upcoming tracks**\n" + "\n".join(lines))

@bot.tree.command(name="stop", description="Stop music, clear the queue, and leave voice")
async def stop(interaction: discord.Interaction):
    if not interaction.guild:
        await interaction.response.send_message("Use this in a server.", ephemeral=True)
        return
    queues[interaction.guild_id] = deque()
    voice = interaction.guild.voice_client
    if voice:
        await voice.disconnect(force=True)
    await interaction.response.send_message("⏹️ Stopped, queue cleared, and disconnected.")

@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    message = str(getattr(error, "original", error))
    try:
        if interaction.response.is_done():
            await interaction.followup.send(message, ephemeral=True)
        else:
            await interaction.response.send_message(message, ephemeral=True)
    except discord.HTTPException:
        logging.exception("Could not send command error")

if not TOKEN:
    raise RuntimeError("DISCORD_TOKEN environment variable is missing.")
bot.run(TOKEN)
