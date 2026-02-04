import asyncio
import os
from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Deque, Optional

import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
from yt_dlp import YoutubeDL

load_dotenv()

INTENTS = discord.Intents.default()
INTENTS.message_content = False

BOT = commands.Bot(command_prefix="!", intents=INTENTS)

SPOTIFY_CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID")
SPOTIFY_CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET")

YTDL_OPTS = {
    "format": "bestaudio/best",
    "noplaylist": True,
    "quiet": True,
    "default_search": "ytsearch",
}

FFMPEG_OPTS = {
    "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
    "options": "-vn",
}


@dataclass
class Track:
    title: str
    url: str
    source_url: str


class GuildQueue:
    def __init__(self) -> None:
        self.queue: Deque[Track] = deque()
        self.current: Optional[Track] = None
        self.play_lock = asyncio.Lock()


guild_queues: dict[int, GuildQueue] = defaultdict(GuildQueue)


@BOT.event
async def on_ready() -> None:
    await BOT.tree.sync()
    print(f"Logged in as {BOT.user}")


def spotify_client() -> spotipy.Spotify:
    if not SPOTIFY_CLIENT_ID or not SPOTIFY_CLIENT_SECRET:
        raise RuntimeError("Spotify credentials not configured.")
    auth_manager = SpotifyClientCredentials(
        client_id=SPOTIFY_CLIENT_ID,
        client_secret=SPOTIFY_CLIENT_SECRET,
    )
    return spotipy.Spotify(auth_manager=auth_manager)


def is_spotify_url(query: str) -> bool:
    return "open.spotify.com" in query


def extract_spotify_tracks(query: str) -> list[str]:
    client = spotify_client()
    if "track" in query:
        track = client.track(query)
        return [f"{track['name']} {track['artists'][0]['name']}"]
    if "playlist" in query:
        items = client.playlist_items(query)
        return [
            f"{item['track']['name']} {item['track']['artists'][0]['name']}"
            for item in items["items"]
            if item.get("track")
        ]
    if "album" in query:
        items = client.album_tracks(query)
        return [
            f"{item['name']} {item['artists'][0]['name']}"
            for item in items["items"]
        ]
    return []


def resolve_track(query: str) -> Track:
    with YoutubeDL(YTDL_OPTS) as ytdl:
        info = ytdl.extract_info(query, download=False)
    if "entries" in info:
        info = info["entries"][0]
    return Track(
        title=info.get("title", "Unknown"),
        url=info["url"],
        source_url=info.get("webpage_url", query),
    )


async def ensure_voice(interaction: discord.Interaction) -> discord.VoiceClient:
    if not interaction.user or not isinstance(interaction.user, discord.Member):
        raise app_commands.AppCommandError("Only server members can use this.")
    if not interaction.user.voice or not interaction.user.voice.channel:
        raise app_commands.AppCommandError("Join a voice channel first.")
    if interaction.guild is None:
        raise app_commands.AppCommandError("This command must be used in a server.")
    voice_client = interaction.guild.voice_client
    if voice_client and voice_client.channel != interaction.user.voice.channel:
        await voice_client.move_to(interaction.user.voice.channel)
    if voice_client is None:
        voice_client = await interaction.user.voice.channel.connect()
    return voice_client


async def play_next(guild_id: int, voice_client: discord.VoiceClient) -> None:
    queue = guild_queues[guild_id]
    async with queue.play_lock:
        if queue.current is None and queue.queue:
            queue.current = queue.queue.popleft()
        track = queue.current
        if track is None:
            return
        source = discord.FFmpegPCMAudio(track.url, **FFMPEG_OPTS)
        def after_playback(error: Optional[Exception]) -> None:
            if error:
                print(f"Playback error: {error}")
            queue.current = None
            BOT.loop.create_task(play_next(guild_id, voice_client))
        voice_client.play(source, after=after_playback)


@BOT.tree.command(name="play", description="Play a search query or Spotify link.")
@app_commands.describe(query="Search query or Spotify URL")
async def play(interaction: discord.Interaction, query: str) -> None:
    await interaction.response.defer()
    voice_client = await ensure_voice(interaction)
    queue = guild_queues[interaction.guild_id]

    search_terms: list[str]
    if is_spotify_url(query):
        search_terms = extract_spotify_tracks(query)
    else:
        search_terms = [query]

    if not search_terms:
        await interaction.followup.send("No tracks found for that link.")
        return

    for term in search_terms:
        track = await asyncio.to_thread(resolve_track, term)
        queue.queue.append(track)

    if not voice_client.is_playing() and queue.current is None:
        await play_next(interaction.guild_id, voice_client)

    await interaction.followup.send(f"Queued {len(search_terms)} track(s).")


@BOT.tree.command(name="pause", description="Pause playback.")
async def pause(interaction: discord.Interaction) -> None:
    voice_client = await ensure_voice(interaction)
    voice_client.pause()
    await interaction.response.send_message("Paused.")


@BOT.tree.command(name="resume", description="Resume playback.")
async def resume(interaction: discord.Interaction) -> None:
    voice_client = await ensure_voice(interaction)
    voice_client.resume()
    await interaction.response.send_message("Resumed.")


@BOT.tree.command(name="skip", description="Skip the current track.")
async def skip(interaction: discord.Interaction) -> None:
    voice_client = await ensure_voice(interaction)
    voice_client.stop()
    await interaction.response.send_message("Skipped.")


@BOT.tree.command(name="stop", description="Stop playback and clear queue.")
async def stop(interaction: discord.Interaction) -> None:
    voice_client = await ensure_voice(interaction)
    queue = guild_queues[interaction.guild_id]
    queue.queue.clear()
    queue.current = None
    voice_client.stop()
    await voice_client.disconnect()
    await interaction.response.send_message("Stopped and cleared the queue.")


@BOT.tree.command(name="queue", description="Show the current queue.")
async def show_queue(interaction: discord.Interaction) -> None:
    queue = guild_queues[interaction.guild_id]
    if queue.current is None and not queue.queue:
        await interaction.response.send_message("Queue is empty.")
        return
    lines = []
    if queue.current:
        lines.append(f"**Now Playing:** {queue.current.title}")
    if queue.queue:
        lines.append("**Up Next:**")
        lines.extend(f"- {track.title}" for track in list(queue.queue)[:10])
    await interaction.response.send_message("\n".join(lines))


@BOT.tree.command(name="nowplaying", description="Show the current track.")
async def now_playing(interaction: discord.Interaction) -> None:
    queue = guild_queues[interaction.guild_id]
    if queue.current is None:
        await interaction.response.send_message("Nothing is playing.")
        return
    await interaction.response.send_message(
        f"Now playing: **{queue.current.title}**\n<{queue.current.source_url}>"
    )


def main() -> None:
    token = os.getenv("DISCORD_BOT_TOKEN")
    if not token:
        raise RuntimeError("DISCORD_BOT_TOKEN is required.")
    BOT.run(token)


if __name__ == "__main__":
    main()
