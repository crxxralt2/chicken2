# Discord Token Controller

This repository provides a small controller bot and a token runner that can start multiple Discord clients from tokens stored in `data/config.json`.

Important: Storing Discord tokens is sensitive. Keep `data/config.json` private and do not share it.

Files:
- `data/config.json`: config with `controller_token` and `tokens` array.
- `src/bot.py`: controller bot that responds to `!addtoken`, `!runtokens`, and `!listtokens` (owner-only commands).
- `src/token_runner.py`: starts clients for each token in background tasks and exposes `online_users`.

Setup:
1. Install dependencies:
```
pip install -r requirements.txt
```
2. Set your controller bot token. For local testing edit `data/config.json` and set `controller_token`,
   or when deploying (e.g. Railway) set the environment variable `CONTROLLER_TOKEN`.
3. Run the site and controller locally:
```
uvicorn src.web:app --host 0.0.0.0 --port 5000
```

Web Server:
- The project now uses FastAPI with `uvicorn` for production-ready hosting.
- Access it at `http://localhost:5000` or `https://<your-railway-domain>/`
- Routes:
  - `/` — bot status and info
  - `/storage` — view stored tokens (masked)
  - `/help` — view all bot commands

Usage (in Discord):
- `!h` — show all available commands and setup steps
- `!addtoken <token> [label]` — add token with optional label (friendly name).
- `!runtokens` — launches clients for all stored tokens.
- `!listtokens` — lists stored tokens (masked) and their DB ids.

Per-token commands:
- `!runtoken <tokenid>` — start a specific token client.
- `!joinvc_token <tokenid>` — make a specific token join your current voice channel.
- `!joinsv <tokenid> <serverlink>` — make a specific token join a server via invite link.
- `!say <tokenid> <userid> <message>` — send a DM via a specific token to a user.

Token management:
- `!rmtoken <id|token>` — remove a stored token by DB id or by full token string.
- `!exportconfig` — export stored tokens into `data/config.json` under `tokens`.
- `!importconfig` — import tokens from `data/config.json` into the DB.

Persistence:
- Tokens added with `!addtoken` are stored in `data/tokens.db` (SQLite). This allows the controller to be redeployed (for example on Railway) without re-adding tokens.

Voice join behaviour
- When token clients join a voice channel via `!joinvc` or `!joinvc_token`, they will play a TTS announcement: "Check my bio for a really cool server!" 5 times with a 30 second cooldown between each play, then disconnect.

Prerequisites for voice/TTS
- `ffmpeg` must be available on the host for `discord.FFmpegPCMAudio` to work. On Railway, add an install step or use a buildpack that provides `ffmpeg`.
- Python packages: `gTTS` and `PyNaCl` are included in `requirements.txt`.

Deploying on Railway
1. Create a new Railway project and connect your GitHub repo (crxxralt1/chicken).
2. Railway will auto-detect the `Procfile` and start the site and bot.
3. Set environment variables in Railway:
   - `CONTROLLER_TOKEN` = your Discord controller bot token (required)
   - `PORT` = (optional, defaults to 5000)
4. Deploy — Railway will automatically run `uvicorn src.web:app --host 0.0.0.0 --port $PORT`
5. Access your web dashboard at: `https://<your-railway-domain>/`

**Quick Railway Setup:**
- Go to [Railway.app](https://railway.app)
- Click "New Project" → "Deploy from GitHub"
- Select `crxxralt1/chicken`
- Add environment variables (see step 3 above)
- Click deploy
- View logs and live status in Railway dashboard

Security and policy note:
- This tool runs client connections for tokens you provide. Do not use tokens for other users, and ensure you comply with Discord's Terms of Service.
