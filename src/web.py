import os
import asyncio
from pathlib import Path
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from src.bot import bot, data
from src import db, token_runner

app = FastAPI(title='Discord Token Controller')

TEMPLATE_DIR = Path(__file__).resolve().parent.parent / 'templates'


def load_template(name: str) -> str:
    path = TEMPLATE_DIR / name
    return path.read_text(encoding='utf-8')


@app.get('/', response_class=HTMLResponse)
def home():
    rows = db.list_tokens_sync()
    active_clients = len(token_runner.clients)
    content = load_template('index.html').format(active_clients=active_clients, token_count=len(rows))
    return HTMLResponse(content=content)


@app.get('/storage', response_class=HTMLResponse)
def storage():
    rows = db.list_tokens_sync()
    if not rows:
        token_rows = '<p>No tokens stored yet.</p>'
    else:
        row_html = '<table>\n            <tr>\n                <th>ID</th>\n                <th>Token (Masked)</th>\n                <th>Label</th>\n                <th>Added</th>\n            </tr>\n'
        for row in rows:
            token = row['token']
            masked = token[:4] + '...' + token[-4:] if len(token) > 8 else '****'
            label = row['label'] or 'N/A'
            added_at = row['added_at'][:10] if row['added_at'] else ''
            row_html += f'            <tr>\n                <td>{row["id"]}</td>\n                <td class="token">{masked}</td>\n                <td>{label}</td>\n                <td>{added_at}</td>\n            </tr>\n'
        row_html += f'        </table>\n        <p><b>Total:</b> {len(rows)} tokens stored</p>\n'
        token_rows = row_html

    content = load_template('storage.html').format(token_rows=token_rows)
    return HTMLResponse(content=content)


@app.get('/help', response_class=HTMLResponse)
def help_page():
    content = load_template('help.html')
    return HTMLResponse(content=content)


async def _start_controller_bot():
    controller_token = os.environ.get('CONTROLLER_TOKEN') or data.get('controller_token')
    if not controller_token:
        raise RuntimeError('CONTROLLER_TOKEN must be set as an environment variable for deployment.')
    print('[web] Starting controller bot')
    try:
        await bot.start(controller_token)
    except Exception as exc:
        print(f'[web] Controller bot failed to start: {exc}')
        raise


@app.on_event('startup')
async def startup_event():
    if getattr(app.state, 'bot_task', None) is None:
        app.state.bot_task = asyncio.create_task(_start_controller_bot())


@app.on_event('shutdown')
async def shutdown_event():
    if getattr(app.state, 'bot_task', None) is not None:
        await bot.close()
        app.state.bot_task.cancel()
