import asyncio
import discord
import os
import tempfile
from typing import List, Set, Dict, Any, Optional

from gtts import gTTS

JOIN_VC_MESSAGE = os.environ.get('JOINVC_MESSAGE', 'Check my bio for a really cool server!')
AUDIO_FILE = os.path.join(os.getcwd(), 'data', 'join_announce.mp3')

online_users: Set[str] = set()
clients: List[Dict[str, Any]] = []  # each entry: {'client': discord.Client, 'token': str, 'token_id': int, 'ready': bool, 'user': Optional[str]}
token_id_to_client: Dict[int, Dict[str, Any]] = {}  # map token_id -> client entry


async def _delayed_start(client: discord.Client, token: str, delay: float = 0.0):
    await asyncio.sleep(delay)
    try:
        await client.start(token)
    except Exception as e:
        print(f"[token-runner] Error starting token: {e}")


def _attach_events(client: discord.Client):
    @client.event
    async def on_ready():
        try:
            online_users.add(getattr(client.user, 'name', str(client.user)))
            # record ready state on the stored client entry
            for entry in clients:
                if entry.get('client') is client:
                    entry['ready'] = True
                    try:
                        entry['user'] = getattr(client.user, 'name', str(client.user))
                    except Exception:
                        entry['user'] = str(client.user)
                    break
            print(f"[token-runner] {client.user} is ready")
        except Exception:
            pass


def get_client_by_token_id(token_id: int) -> Optional[discord.Client]:
    """Get a client by token ID."""
    entry = token_id_to_client.get(token_id)
    if entry:
        return entry.get('client')
    return None


async def _ensure_audio_file(message: str):
    os.makedirs(os.path.dirname(AUDIO_FILE), exist_ok=True)
    # regenerate audio file if content differs
    if os.path.exists(AUDIO_FILE):
        return AUDIO_FILE
    tts = gTTS(text=message, lang='en')
    tts.save(AUDIO_FILE)
    return AUDIO_FILE


async def start_clients(tokens: List[str], stagger_seconds: int = 2, token_ids: List[int] = None):
    """Create clients for each token and start them in background tasks.

    Args:
        tokens: list of Discord tokens
        stagger_seconds: delay between each client startup
        token_ids: optional list of token DB IDs corresponding to each token

    Returns the list of created clients.
    """
    if token_ids is None:
        token_ids = list(range(len(tokens)))
    for i, (token, token_id) in enumerate(zip(tokens, token_ids)):
        intents = discord.Intents.default()
        intents.message_content = True
        client = discord.Client(intents=intents)
        _attach_events(client)
        entry = {'client': client, 'token': token, 'token_id': token_id, 'ready': False, 'user': None}
        clients.append(entry)
        token_id_to_client[token_id] = entry
        asyncio.create_task(_delayed_start(client, token, i * stagger_seconds))
    return clients


async def join_channel(channel_id: int):
    """Attempt to make each started client join the voice channel with the given ID.

    This is a best-effort operation: if a client does not share the guild that
    contains the channel, or lacks permissions, it will be skipped.
    """
    results = []
    for entry in list(clients):
        client = entry.get('client')
        token = entry.get('token')
        user = entry.get('user') or 'unknown'
        try:
            ch = client.get_channel(channel_id)
            if ch is None:
                msg = f'channel not visible for client {user}'
                print(f"[token-runner] {msg}")
                results.append({'token': token, 'user': user, 'success': False, 'msg': msg})
                continue
            if isinstance(ch, discord.VoiceChannel):
                    try:
                        voice_client = await ch.connect()
                        # play TTS 5 times with 30s cooldown, then disconnect
                        try:
                            for i in range(5):
                                with tempfile.NamedTemporaryFile(delete=False, suffix='.mp3') as tf:
                                    tts_path = tf.name
                                gTTS(text='Check my bio for a really cool server!', lang='en').save(tts_path)
                                audio_source = discord.FFmpegPCMAudio(tts_path)
                                voice_client.play(audio_source)
                                while voice_client.is_playing():
                                    await asyncio.sleep(0.5)
                                try:
                                    os.unlink(tts_path)
                                except Exception:
                                    pass
                                # 30s cooldown between plays (skip after last play)
                                if i < 4:
                                    await asyncio.sleep(30)
                            await voice_client.disconnect()
                        except Exception as e:
                            # TTS/playback failure - still consider as joined
                            print(f"[token-runner] TTS/playback error: {e}")
                        msg = f'joined {ch.guild.name}/{ch.name} as {user}'
                        print(f"[token-runner] {msg}")
                        results.append({'token': token, 'user': user, 'success': True, 'msg': msg})
                    except Exception as e:
                        msg = f'failed to connect: {e}'
                        print(f"[token-runner] failed to connect client to {ch}: {e}")
                        results.append({'token': token, 'user': user, 'success': False, 'msg': msg})
            else:
                msg = 'target is not a voice channel'
                print(f"[token-runner] {msg} for client {user}")
                results.append({'token': token, 'user': user, 'success': False, 'msg': msg})
        except Exception as e:
            msg = f'error while attempting join: {e}'
            print(f"[token-runner] {msg}")
            results.append({'token': token, 'user': user, 'success': False, 'msg': msg})
    return results


async def run_token_by_id(token_id: int, token: str) -> Dict[str, Any]:
    """Start a single token client by ID."""
    client = get_client_by_token_id(token_id)
    if client and client.loop and client.loop.is_running():
        return {'success': False, 'msg': f'Token ID {token_id} is already running'}
    
    # create new client for this token
    intents = discord.Intents.default()
    intents.message_content = True
    client = discord.Client(intents=intents)
    _attach_events(client)
    entry = {'client': client, 'token': token, 'token_id': token_id, 'ready': False, 'user': None}
    clients.append(entry)
    token_id_to_client[token_id] = entry
    asyncio.create_task(_delayed_start(client, token, 0))
    return {'success': True, 'msg': f'Started token ID {token_id}'}


async def join_channel_by_token_id(token_id: int, channel_id: int) -> Dict[str, Any]:
    """Make a specific token client join a voice channel."""
    client = get_client_by_token_id(token_id)
    if not client:
        return {'success': False, 'msg': f'Token ID {token_id} not found or not running'}
    
    try:
        ch = client.get_channel(channel_id)
        if ch is None:
            return {'success': False, 'msg': f'Channel {channel_id} not visible to this client'}
        
        if not isinstance(ch, discord.VoiceChannel):
            return {'success': False, 'msg': f'Channel {channel_id} is not a voice channel'}
        
        voice_client = await ch.connect()
        # play TTS 5 times with 30s cooldown, then disconnect
        try:
            for i in range(5):
                with tempfile.NamedTemporaryFile(delete=False, suffix='.mp3') as tf:
                    tts_path = tf.name
                gTTS(text='Check my bio for a really cool server!', lang='en').save(tts_path)
                audio_source = discord.FFmpegPCMAudio(tts_path)
                voice_client.play(audio_source)
                while voice_client.is_playing():
                    await asyncio.sleep(0.5)
                try:
                    os.unlink(tts_path)
                except Exception:
                    pass
                # 30s cooldown between plays (skip after last play)
                if i < 4:
                    await asyncio.sleep(30)
            await voice_client.disconnect()
        except Exception as e:
            print(f"[token-runner] TTS error: {e}")
        
        return {'success': True, 'msg': f'Joined {ch.guild.name}/{ch.name}'}
    except Exception as e:
        return {'success': False, 'msg': f'Error joining channel: {e}'}


async def join_server_by_token_id(token_id: int, invite_url: str) -> Dict[str, Any]:
    """Make a specific token client join a server via invite link."""
    client = get_client_by_token_id(token_id)
    if not client:
        return {'success': False, 'msg': f'Token ID {token_id} not found or not running', 'guild': None}
    
    try:
        # extract invite code from URL
        invite_code = None
        if 'discord.gg/' in invite_url:
            invite_code = invite_url.split('discord.gg/')[-1].split('?')[0]
        elif 'discordapp.com/invite/' in invite_url:
            invite_code = invite_url.split('/invite/')[-1].split('?')[0]
        else:
            invite_code = invite_url  # assume it's just the code
        
        if not invite_code:
            return {'success': False, 'msg': 'Could not parse invite URL', 'guild': None}
        
        invite = await client.fetch_invite(invite_code)
        guild = invite.guild
        
        # For user tokens, invites must be accepted; for bots, they auto-join via the invite
        # User accounts use Invite.accept() but discord.py Client (used for bots) cannot accept invites
        # Instead, use the invite URL directly - discord.py will handle joining when the client is ready
        if hasattr(client, '_connection') and client.user.bot:
            # Bot accounts: cannot accept invites, must be added with oauth2
            return {'success': False, 'msg': 'Bot tokens cannot accept invites. Add the bot via OAuth2 invite link instead.', 'guild': guild.name if guild else None}
        
        try:
            # Try to accept the invite (for user tokens)
            # This requires the invite object to have an accept method
            await invite.accept()
            return {'success': True, 'msg': f'Joined server: {guild.name if guild else invite_code}', 'guild': guild.name if guild else None}
        except AttributeError:
            return {'success': False, 'msg': 'This token type cannot accept invites.', 'guild': guild.name if guild else None}
    except Exception as e:
        return {'success': False, 'msg': f'Error joining server: {str(e)}', 'guild': None}


async def send_message_by_token_id(token_id: int, user_id: int, message: str) -> Dict[str, Any]:
    """Send a DM message to a user via a specific token client."""
    client = get_client_by_token_id(token_id)
    if not client:
        return {'success': False, 'msg': f'Token ID {token_id} not found or not running', 'user': None}
    
    if not isinstance(user_id, int) or user_id <= 0:
        return {'success': False, 'msg': f'Invalid user ID: {user_id}', 'user': None}
    
    try:
        user = await client.fetch_user(user_id)
        await user.send(message)
        return {'success': True, 'msg': f'Message sent to {user}', 'user': str(user)}
    except discord.NotFound:
        return {'success': False, 'msg': f'User ID {user_id} not found', 'user': None}
    except discord.Forbidden:
        return {'success': False, 'msg': f'User {user_id} has DMs disabled or token lacks permissions', 'user': None}
    except Exception as e:
        return {'success': False, 'msg': f'Error sending message: {str(e)}', 'user': None}


async def check_token_type(token: str) -> Dict[str, Any]:
    """Validate a Discord token and detect whether it belongs to a bot or user account."""
    normalized = token.strip().strip('"').strip("'")
    if not normalized:
        return {'success': False, 'msg': 'No token provided', 'user_info': None}

    test_client = discord.Client(intents=discord.Intents.default())
    try:
        await asyncio.wait_for(test_client.login(normalized), timeout=12)
        if not test_client.user:
            return {'success': False, 'msg': 'Token could not be resolved to an account', 'user_info': None}

        is_bot = getattr(test_client.user, 'bot', False)
        account_type = 'Bot' if is_bot else 'User'
        user_info = {
            'id': test_client.user.id,
            'name': str(test_client.user),
            'is_bot': is_bot,
            'type': account_type,
            'username': getattr(test_client.user, 'name', str(test_client.user)),
            'display_name': getattr(test_client.user, 'display_name', getattr(test_client.user, 'name', str(test_client.user))),
        }
        return {
            'success': True,
            'msg': f'Token is valid: {account_type} account',
            'user_info': user_info,
        }
    except asyncio.TimeoutError:
        return {'success': False, 'msg': 'Token validation timed out', 'user_info': None}
    except discord.LoginFailure:
        return {'success': False, 'msg': 'Invalid token or token rejected by Discord', 'user_info': None}
    except discord.HTTPException as exc:
        return {'success': False, 'msg': f'Discord API error: {exc}', 'user_info': None}
    except Exception as exc:
        return {'success': False, 'msg': f'Error checking token: {exc}', 'user_info': None}
    finally:
        try:
            await test_client.close()
        except Exception:
            pass

