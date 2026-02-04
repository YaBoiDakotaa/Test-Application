# Personal Discord Spotify-Style Bot

A starter Discord music bot that behaves like a lightweight Spotify experience: queues tracks, supports search, shows now playing, and can ingest Spotify links (playlist/track/album) to build a playable queue.

> **Important**: Spotify does **not** provide audio streams. This bot resolves Spotify links into a searchable track list and plays audio from a separate source (e.g., YouTube) using `yt-dlp`.

## Features
- `/play <query or spotify url>`: search or expand Spotify links into a queue
- `/pause`, `/resume`, `/skip`, `/stop`
- `/queue`, `/nowplaying`

## Setup
1. **Create a Discord application** and bot token at <https://discord.com/developers/applications>.
2. **Create Spotify app credentials** at <https://developer.spotify.com/dashboard>.
3. **Install dependencies**:
   ```bash
   python -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```
4. **Set environment variables** (see `.env.example`).
5. **Run the bot**:
   ```bash
   python bot.py
   ```

## Notes
- This is a minimal, personal-use starter. Add moderation, permissions, and hosting as needed.
- For production, prefer a Lavalink node (or similar) for reliable audio streaming.
