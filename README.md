# SkyBot — Search + Music Discord Bot

A Discord bot with web search and voice music commands.

## Commands

- `/help` — show command help.
- `/google query` — return up to five web search results.
- `/play query_or_link` — search YouTube for a song or play a YouTube URL.
- `/skip`, `/pause`, `/resume` — control playback.
- `/queue` — show queued tracks.
- `/stop` — clear the queue and disconnect.

Join a voice channel before using `/play`.

### Spotify support

Individual Spotify track links can be supported if Spotify Developer API credentials are configured. The bot reads the track title and artist, then searches YouTube for a playable match. It does **not** stream audio from Spotify. Spotify playlist and album URLs are not supported by this starter version.

## 1. Create and invite the Discord bot

1. Open the [Discord Developer Portal](https://discord.com/developers/applications) and create an application.
2. Open **Bot** and create the bot if prompted. Copy its token privately.
3. Under **Installation** or **OAuth2 URL Generator**, select the `bot` and `applications.commands` scopes.
4. Grant **View Channels**, **Send Messages**, **Embed Links**, **Connect**, and **Speak** permissions.
5. Use the generated install link to add the bot to your server.

**Never commit your real bot token or Spotify client secret to GitHub.** If a token is exposed, reset it immediately in the relevant developer dashboard.

## 2. Deploy on Railway (or another persistent Docker host)

1. Create a project/service on your hosting provider and connect this repository: [TwilightRavennMiya/SkyBot](https://github.com/TwilightRavennMiya/SkyBot).
2. Deploy using the repository's root `Dockerfile`.
3. In the service's **Variables** settings, add:
   - `DISCORD_TOKEN` — required Discord bot token.
   - `SPOTIFY_CLIENT_ID` — optional.
   - `SPOTIFY_CLIENT_SECRET` — optional.
4. Deploy/redeploy and inspect logs. A successful start should show the bot logged in and slash commands synced.
5. Choose a plan that supports a continuously running service. Free tiers may sleep or have usage limits, so check current pricing and limits with the host.

Do not deploy this as a short-lived serverless function; voice connections need a persistent process.

## 3. Optional Spotify setup

1. Open the [Spotify Developer Dashboard](https://developer.spotify.com/dashboard) and create an app if your account is eligible.
2. Copy its Client ID and Client Secret.
3. Add them as the optional environment variables above and redeploy.

## Run locally (optional)

Install Python 3.12 and FFmpeg, then run:

```bash
python -m venv .venv
```

Windows PowerShell:

```powershell
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:DISCORD_TOKEN="YOUR_BOT_TOKEN"
python bot.py
```

macOS/Linux:

```bash
source .venv/bin/activate
pip install -r requirements.txt
export DISCORD_TOKEN="YOUR_BOT_TOKEN"
python bot.py
```

## Troubleshooting

- **Slash commands missing:** confirm the bot is online and was invited with `applications.commands`; wait briefly and check logs.
- **Bot cannot join or play audio:** check Connect/Speak permissions and confirm the Docker service is running.
- **Web search fails:** the search provider may be temporarily unavailable or rate-limiting requests.
- **YouTube playback stops working:** update `yt-dlp` in `requirements.txt` and redeploy.
- **Bot is offline:** inspect the hosting service logs and confirm the service is persistent rather than sleeping.

## Project files

- `bot.py` — commands, web search, and playback logic.
- `requirements.txt` — Python dependencies.
- `Dockerfile` — installs FFmpeg and runs the bot.
- `.env.example` — variable-name template only; it contains no real credentials.
