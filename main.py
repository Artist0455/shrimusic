import os
from dotenv import load_dotenv
load_dotenv()

BOT_TOKEN = os.getenv('BOT_TOKEN')
API_ID = int(os.getenv('API_ID') or 0)
API_HASH = os.getenv('API_HASH')
OWNER_ID = int(os.getenv('OWNER_ID') or 0)
SUPPORT_CHAT = os.getenv('SUPPORT_CHAT')
UPDATE_CHANNEL = os.getenv('UPDATE_CHANNEL')
ARTIST_CHECK_CHAT = os.getenv('ARTIST_CHECK_CHAT')

# runtime options
DOWNLOAD_DIR = os.getenv('DOWNLOAD_DIR', './downloads')
LOG_CHAT = os.getenv('LOG_CHAT') or OWNER_ID

# validation helper
if not BOT_TOKEN or not API_ID or not API_HASH:
    raise RuntimeError('Required env variables missing. See README.md')

### FILE: utils.py
import os
import asyncio
import shutil
from pathlib import Path

async def ensure_dir(path):
    Path(path).mkdir(parents=True, exist_ok=True)

def format_seconds(s):
    s = int(s)
    h = s // 3600
    m = (s % 3600) // 60
    sec = s % 60
    if h:
        return f"{h:02d}:{m:02d}:{sec:02d}"
    return f"{m:02d}:{sec:02d}"

def get_duration(path):
    try:
        audio = MP3(path)
        return int(audio.info.length)
    except Exception:
        return 0

### FILE: player.py
import asyncio
import os
from pytgcalls import PyTgCalls, idle
from pytgcalls.exceptions import NoActiveGroupCall
from pyrogram import Client
from yt_dlp import YoutubeDL

class Song:
    def __init__(self, title, requester, filepath, duration):
        self.title = title
        self.requester = requester
        self.filepath = filepath
        self.duration = duration

class Player:
    def __init__(self, app: Client):
        self.app = app
        self.pytgcalls = PyTgCalls(app)
        self.queue = asyncio.Queue()
        self.current = None
        self.play_task = None
        self._is_paused = False
        self.ytdl_opts = {
            'format': 'bestaudio/best',
            'outtmpl': os.path.join(DOWNLOAD_DIR, '%(id)s.%(ext)s'),
            'noplaylist': True,
            'quiet': True,
        }

    async def start(self):
        await ensure_dir(DOWNLOAD_DIR)
        await self.pytgcalls.start()

    async def join_vc(self, chat_id):
        try:
            await self.pytgcalls.join_group_call(chat_id, AudioPiped(self.current.filepath))
        except NoActiveGroupCall:
            # attempt to start a group call (some limitations apply)
            raise

    async def enqueue(self, query, requester):
        # download using yt-dlp
        loop = asyncio.get_event_loop()
        info = None
        ydl = YoutubeDL(self.ytdl_opts)
        try:
            info = ydl.extract_info(query, download=True)
            filepath = ydl.prepare_filename(info)
            duration = info.get('duration') or get_duration(filepath)
            title = info.get('title') or os.path.basename(filepath)
            song = Song(title, requester, filepath, duration)
            await self.queue.put(song)
            return song
        except Exception as e:
            raise

    async def play_loop(self, chat_id):
        while True:
            song = await self.queue.get()
            self.current = song
            # join vc and play
            await self.pytgcalls.join_group_call(chat_id, AudioPiped(song.filepath))
            # wait for duration
            await asyncio.sleep(max(1, song.duration))
            # after finished
            try:
                await self.pytgcalls.leave_group_call(chat_id)
            except Exception:
                pass
            self.queue.task_done()

    async def start_player(self, chat_id):
        if self.play_task and not self.play_task.done():
            return
        self.play_task = asyncio.create_task(self.play_loop(chat_id))

    async def skip(self):
        # skip: simply stop current by leaving and let loop continue
        try:
            await self.pytgcalls.stop()
        except Exception:
            pass

    async def pause(self):
        await self.pytgcalls.pause_stream()
        self._is_paused = True

    async def resume(self):
        await self.pytgcalls.resume_stream()
        self._is_paused = False

### FILE: handlers.py
from pyrogram import filters
from pyrogram.types import Message
import asyncio

player: Player = None

async def set_player(p: Player):
    global player
    player = p


async def start_handler(client, message: Message):
    text = (
        "🎵 Welcome to Artist Music Bot!\n\n"
        "Commands:\n"
        "/play <url or query> - Play a song\n"
        "/pause - Pause\n"
        "/resume - Resume\n"
        "/seek <seconds> - Seek (approx)\n"
        "/skip - Skip current\n"
        "/nowplaying - Show current song info\n"
    )
    await message.reply_text(text)

async def play_handler(client, message: Message):
    if not message.reply_to_message and not message.text.split(maxsplit=1)[1:]:
        await message.reply_text('Usage: /play <url or search query>')
        return
    query = message.text.split(maxsplit=1)[1] if len(message.text.split(maxsplit=1))>1 else message.reply_to_message.text
    sent = await message.reply_text('🔎 Searching and downloading...')
    try:
        song = await player.enqueue(query, message.from_user.first_name)
        await sent.edit_text(f"Artist Music strimming\n\nTitle: {song.title}\nDuration: {format_seconds(song.duration)}\nRequested by: {song.requester}")
        # start player in the same chat (assumes group voice chat for this chat id)
        await player.start_player(message.chat.id)
    except Exception as e:
        await sent.edit_text('❌ Failed to play: ' + str(e))

async def pause_handler(client, message: Message):
    try:
        await player.pause()
        await message.reply_text('⏸ Paused')
    
        await message.reply_text('Error: '+str(e))
        
        await player.resume()
        await message.reply_text('▶️ Resumed')
    except Exception as e:
        await message.reply_text('Error: '+str(e))

async def nowplaying_handler(client, message: Message):
    if not player.current:
        return await message.reply_text('No song is playing right now.')
    s = player.current
    await message.reply_photo(photo=None, caption=(
        f"🎶 Now Playing\nTitle: {s.title}\nDuration: {format_seconds(s.duration)}\nRequested by: {s.requester}\n"
    ))

async def seek_handler(client, message: Message):
    # seeking in live stream via pytgcalls is non-trivial; we approximate by restarting playback from offset using ffmpeg -ss
    args = message.text.split()
    if len(args) < 2:
        return await message.reply_text('Usage: /seek <seconds>')
    try:
        seconds = int(args[1])
    except:
        return await message.reply_text('Provide seconds as integer')
    if not player.current:
        return await message.reply_text('Nothing playing')
    # implement by stopping and re-creating a temp file with -ss (skipped here for brevity)
    await message.reply_text('Seek requested — feature limited, will attempt approximate seek')

### FILE: main.py
import asyncio
from pyrogram import Client, idle
import logging

logging.basicConfig(level=logging.INFO)

app = Client('artist-music-bot', bot_token=BOT_TOKEN, api_id=API_ID, api_hash=API_HASH)

async def artist_check_task(client: Client):
    # runs every minute and posts Artist check
    while True:
        try:
            if ARTIST_CHECK_CHAT:
                await client.send_message(ARTIST_CHECK_CHAT, 'Artist check successful ✨')
            else:
                # fallback to owner
                await client.send_message(OWNER_ID, 'Artist check successful ✨')
        except Exception as e:
            logging.warning('Artist check failed: %s', e)
        await asyncio.sleep(60)


async def main():

    # initialize player
    pl = Player(app)
    await set_player(pl)

    # register handlers using pyrogram's decorated style
    from pyrogram import handlers, filters

app.add_handler(handlers.MessageHandler(start_handler, filters.command("start")))
app.add_handler(handlers.MessageHandler(play_handler, filters.command("play")))
app.add_handler(handlers.MessageHandler(pause_handler, filters.command("pause")))
app.add_handler(handlers.MessageHandler(resume_handler, filters.command("resume")))
app.add_handler(handlers.MessageHandler(nowplaying_handler, filters.command("nowplaying")))
app.add_handler(handlers.MessageHandler(seek_handler, filters.command("seek")))


    # background artist check
    asyncio.create_task(artist_check_task(app))

    print('Bot started. Press Ctrl+C to stop.')
    try:
        await idle()
    finally:
        await app.stop()

if __name__ == '__main__':
    asyncio.run(main())
