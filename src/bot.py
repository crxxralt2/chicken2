
import os
import json
import asyncio
from discord.ext import commands
from discord.ext.commands import CommandInvokeError
import discord
from src import db, token_runner

BASE_DIR = os.path.dirname(os.path.dirname(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, 'data', 'config.json')


def load_config():
    try:
        with open(CONFIG_PATH, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}
    except Exception as exc:
        print(f'[bot] Failed to load config: {exc}')
        return {}


def save_config(data):
    os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
    with open(CONFIG_PATH, 'w') as f:
        json.dump(data, f, indent=2)


data = load_config()

# ensure DB exists
db.ensure_db()

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix='!', intents=intents)


@bot.event
async def on_ready():
    print(f'[controller] Logged in as {bot.user} (id: {bot.user.id})')


@bot.command(name='h')
async def help_cmd(ctx):
    """Show all available commands and setup instructions."""
    help_text = """
**Discord Token Controller Bot — Commands & Setup**

**Setup:**
1. Add tokens: `!addtoken <token> [label]`
2. Start all tokens: `!runtokens`
3. Check stored tokens: `!listtokens`

**Token Management (owner only):**
- `!addtoken <token> [label]` — add a token with optional label
- `!rmtoken <id|token>` — remove token by ID or exact token
- `!listtokens` — list all stored tokens (masked)
- `!exportconfig` — export tokens to data/config.json
- `!importconfig` — import tokens from data/config.json

**Bulk Commands (owner only):**
- `!runtokens` — start all stored token clients
- `!joinvc <channel_name>` — all tokens join a voice channel (plays TTS 5x with 30s cooldown, then leaves)

**Per-Token Commands (owner only):**
- `!runtoken <tokenid>` — start a specific token
- `!joinvc_token <tokenid>` — token joins your current VC (plays TTS 5x with 30s cooldown, then leaves)
- `!joinsv <tokenid> <invite_url>` — token joins a server
- `!say <tokenid> <userid> <message>` — token sends DM to user

**Deploy on Railway:**
- Set env var: `CONTROLLER_TOKEN = your-controller-bot-token`
- Ensure ffmpeg is available in the runtime
- Tokens are persisted in `data/tokens.db`
"""
    await ctx.send(help_text)


@bot.command(name='listc')
async def list_commands(ctx):
    """List the commands that matter most for day-to-day control."""
    embed = discord.Embed(
        title='Essential Commands',
        description='Only the commands an operator typically needs are shown here.',
        color=discord.Color.blue()
    )

    commands_data = {
        'General': [
            ('!h', 'Show setup and command guide'),
            ('!listc', 'Show this command list'),
            ('!checktoken <token>', 'Validate a token and detect bot vs user account'),
        ],
        'Token Storage': [
            ('!addtoken <token> [label]', 'Save a token with an optional label'),
            ('!listtokens', 'Show stored tokens (masked)'),
            ('!rmtoken <id|token>', 'Remove a token by ID or exact value'),
            ('!exportconfig', 'Export tokens to config.json'),
            ('!importconfig', 'Import tokens from config.json'),
        ],
        'Runtime': [
            ('!runtokens', 'Start all saved token clients'),
            ('!runtoken <tokenid>', 'Start one specific token'),
            ('!joinvc <channel_name>', 'Make all active clients join a voice channel'),
            ('!joinvc_token <tokenid>', 'Make one client join your current voice channel'),
        ],
    }

    for category, cmds in commands_data.items():
        field_value = '\n'.join(f'`{cmd}` — {desc}' for cmd, desc in cmds)
        embed.add_field(name=category, value=field_value, inline=False)

    embed.set_footer(text='Advanced DM and invite commands are kept out of this view.')
    await ctx.send(embed=embed)



@bot.command(name='addtoken')
async def addtoken(ctx, token: str, *, label: str = None):
    # add token to persistent DB with optional label
    added = await asyncio.to_thread(db.add_token_sync, token, label)
    if added:
        await ctx.send('Token added to persistent storage.')
    else:
        await ctx.send('Token already exists in storage.')


@bot.command(name='rmtoken')
async def rmtoken(ctx, identifier: str):
    """Remove a stored token by id or by exact token string."""
    # try id first
    removed = False
    if identifier.isdigit():
        removed = await asyncio.to_thread(db.remove_token_by_id_sync, int(identifier))
    if not removed:
        removed = await asyncio.to_thread(db.remove_token_sync, identifier)
    if removed:
        await ctx.send('Token removed.')
    else:
        await ctx.send('No matching token found.')

@bot.command(name='runtokens')
async def runtokens(ctx):
    rows = await asyncio.to_thread(db.list_tokens_sync)
    if not rows:
        await ctx.send('No tokens found in persistent storage.')
        return
    tokens = [r['token'] for r in rows]
    token_ids = [r['id'] for r in rows]
    await ctx.send(f'Starting {len(tokens)} clients...')
    loop = asyncio.get_event_loop()
    loop.create_task(token_runner.start_clients(tokens, token_ids=token_ids))
    await ctx.send('Token clients launched (in background).')


@bot.command(name='listtokens')
async def listtokens(ctx):
    rows = await asyncio.to_thread(db.list_tokens_sync)
    if not rows:
        await ctx.send('No tokens stored.')
        return
    def mask(t: str) -> str:
        if len(t) <= 8:
            return '****'
        return t[:4] + '...' + t[-4:]

    lines = []
    for r in rows[:50]:
        label = f"({r.get('label')})" if r.get('label') else ''
        lines.append(f"{r.get('id')}: {mask(r.get('token'))} {label}")
    if len(rows) > 50:
        lines.append(f"...and {len(rows)-50} more")
    await ctx.send(f'Stored tokens: {len(rows)}\n' + '\n'.join(lines))



@bot.command(name='exportconfig')
async def exportconfig(ctx):
    rows = await asyncio.to_thread(db.list_tokens_sync)
    config = load_config()
    config['tokens'] = [
        {'token': row['token'], 'label': row['label']} if row['label'] else row['token']
        for row in rows
    ]
    save_config(config)
    await ctx.send(f'Exported {len(rows)} tokens to data/config.json.')


@bot.command(name='importconfig')
async def importconfig(ctx):
    config = load_config()
    raw_tokens = config.get('tokens', [])
    added = 0
    for item in raw_tokens:
        if isinstance(item, str):
            token, label = item, None
        elif isinstance(item, dict):
            token = item.get('token')
            label = item.get('label')
        else:
            continue
        if not token:
            continue
        inserted = await asyncio.to_thread(db.add_token_sync, token, label)
        if inserted:
            added += 1
    await ctx.send(f'Imported {added} new tokens from config.')


@bot.command(name='joinvc')
async def joinvc(ctx, *, channel_name: str):
    # find voice channel by name in the guild where command was invoked
    guild = ctx.guild
    if guild is None:
        await ctx.send('This command must be used in a guild.')
        return
    match = discord.utils.get(guild.voice_channels, name=channel_name)
    if match is None:
        await ctx.send(f'Voice channel "{channel_name}" not found in this guild.')
        return
    # instruct token clients to join the channel id and await results
    await ctx.send(f'Instructing clients to join voice channel {match.name}...')
    results = await token_runner.join_channel(match.id)
    success = sum(1 for r in results if r.get('success'))
    fail = len(results) - success
    summary_lines = [f"Success: {success}, Failures: {fail}"]
    # include up to first 10 detailed messages
    for r in results[:10]:
        summary_lines.append(f"{r.get('user')}: {r.get('msg')}")
    if len(results) > 10:
        summary_lines.append(f"...and {len(results)-10} more results")
    await ctx.send('\n'.join(summary_lines))


@bot.command(name='runtoken')
async def runtoken(ctx, token_id: int):
    """Start a specific token by ID."""
    rows = await asyncio.to_thread(db.list_tokens_sync)
    token_row = None
    for r in rows:
        if r['id'] == token_id:
            token_row = r
            break
    if not token_row:
        embed = discord.Embed(color=discord.Color.red(), title='Error', description=f'Token ID {token_id} not found.')
        await ctx.send(embed=embed)
        return
    result = await token_runner.run_token_by_id(token_id, token_row['token'])
    color = discord.Color.green() if result.get('success') else discord.Color.red()
    embed = discord.Embed(color=color, title='Token Status', description=result['msg'])
    await ctx.send(embed=embed)


@bot.command(name='joinvc_token')
async def joinvc_token(ctx, token_id: int):
    """Make a specific token client join the user's current voice channel."""
    if ctx.author.voice is None or ctx.author.voice.channel is None:
        embed = discord.Embed(color=discord.Color.red(), title='Error', description='You must be in a voice channel.')
        await ctx.send(embed=embed)
        return
    channel_id = ctx.author.voice.channel.id
    result = await token_runner.join_channel_by_token_id(token_id, channel_id)
    color = discord.Color.green() if result.get('success') else discord.Color.red()
    embed = discord.Embed(color=color, title='Voice Channel Join', description=result['msg'])
    await ctx.send(embed=embed)


@bot.command(name='joinsv')
async def joinsv(ctx, token_id: int, *, invite_url: str):
    """Make a specific token join a server via invite link."""
    rows = await asyncio.to_thread(db.list_tokens_sync)
    token_row = next((r for r in rows if r['id'] == token_id), None)
    if not token_row:
        embed = discord.Embed(color=discord.Color.red(), title='Error', description=f'Token ID {token_id} not found.')
        await ctx.send(embed=embed)
        return
    result = await token_runner.join_server_by_token_id(token_id, invite_url)
    color = discord.Color.green() if result.get('success') else discord.Color.red()
    embed = discord.Embed(color=color, title='Server Join', description=result['msg'])
    if result.get('guild'):
        embed.add_field(name='Guild', value=result['guild'])
    await ctx.send(embed=embed)


@bot.command(name='say')
async def say(ctx, token_id: int, user_id: int, *, message: str):
    """Send a DM message via a specific token to a user."""
    rows = await asyncio.to_thread(db.list_tokens_sync)
    token_row = next((r for r in rows if r['id'] == token_id), None)
    if not token_row:
        embed = discord.Embed(color=discord.Color.red(), title='Error', description=f'Token ID {token_id} not found.')
        await ctx.send(embed=embed)
        return
    if not isinstance(user_id, int) or user_id <= 0:
        embed = discord.Embed(color=discord.Color.red(), title='Error', description=f'Invalid user ID: {user_id}')
        await ctx.send(embed=embed)
        return
    result = await token_runner.send_message_by_token_id(token_id, user_id, message)
    color = discord.Color.green() if result.get('success') else discord.Color.red()
    embed = discord.Embed(color=color, title='DM Message', description=result['msg'])
    if result.get('user'):
        embed.add_field(name='Recipient', value=result['user'])
    embed.add_field(name='Message', value=message[:1024])
    await ctx.send(embed=embed)


@bot.command(name='checktoken')
async def checktoken(ctx, token: str = None):
    """Check whether a token is valid and identify whether it belongs to a bot or user account."""
    if not token:
        embed = discord.Embed(color=discord.Color.red(), title='Error', description='Please provide a token to check.')
        await ctx.send(embed=embed)
        return

    normalized = token.strip().strip('"').strip("'")
    token_preview = normalized[:10] + '...' + normalized[-4:] if len(normalized) > 14 else '****'

    async with ctx.typing():
        result = await token_runner.check_token_type(normalized)

    if result['success']:
        user_info = result.get('user_info', {})
        color = discord.Color.blue() if user_info.get('is_bot') else discord.Color.purple()
        embed = discord.Embed(color=color, title='Token Info', description=f'Token preview: `{token_preview}`')
        embed.add_field(name='Type', value=user_info.get('type', 'Unknown'), inline=False)
        embed.add_field(name='Username', value=user_info.get('username', user_info.get('name', 'Unknown')), inline=False)
        embed.add_field(name='Display Name', value=user_info.get('display_name', user_info.get('username', 'Unknown')), inline=False)
        embed.add_field(name='User ID', value=f"`{user_info.get('id', 'Unknown')}`", inline=False)
        await ctx.send(embed=embed)
    else:
        embed = discord.Embed(color=discord.Color.red(), title='Error', description=result['msg'])
        await ctx.send(embed=embed)


@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, CommandInvokeError):
        embed = discord.Embed(color=discord.Color.red(), title='Command Error', description=f'{error.original}')
        await ctx.send(embed=embed)
    else:
        embed = discord.Embed(color=discord.Color.red(), title='Error', description=f'{error}')
        await ctx.send(embed=embed)


if __name__ == '__main__':
    # prefer environment variable for deploy platforms like Railway
    controller_token = os.environ.get('CONTROLLER_TOKEN') or data.get('controller_token')
    if not controller_token:
        print('Please set CONTROLLER_TOKEN environment variable or controller_token in data/config.json')
        raise SystemExit(1)
    bot.run(controller_token)
