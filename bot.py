import os
import asyncio
import time
import shutil
import re
from datetime import datetime
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
import yt_dlp
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, filters, ContextTypes
)

# ==================== KONFIGURATSIYA ====================
TOKEN = "8802164056:AAHUzN18Lr5a8S3lhKmuIJ4Ix0OP4X5_Jo4"
DOWNLOAD_DIR = "/tmp/music_bot"
MAX_CONCURRENT = 3  # Bir vaqtda maksimum yuklash
TIMEOUT = 60  # Yuklash timeout (soniya)

# ==================== SOZLAMALAR ====================
os.makedirs(DOWNLOAD_DIR, exist_ok=True)
executor = ThreadPoolExecutor(max_workers=MAX_CONCURRENT)
user_tasks = defaultdict(int)
start_time = time.time()

# ==================== YORDAMCHI FUNKSIYALAR ====================
def get_ffmpeg():
    """FFmpeg ni topish"""
    ffmpeg_paths = [
        shutil.which("ffmpeg"),
        "/usr/bin/ffmpeg",
        "/usr/local/bin/ffmpeg",
        "/opt/homebrew/bin/ffmpeg"
    ]
    for path in ffmpeg_paths:
        if path and os.path.exists(path):
            return path
    return None

FFMPEG = get_ffmpeg()

def human_size(bytes_num):
    """Baytni odam o'qiydigan formatga o'tkazish"""
    for unit in ["B", "KB", "MB", "GB"]:
        if bytes_num < 1024:
            return f"{bytes_num:.1f}{unit}"
        bytes_num /= 1024
    return f"{bytes_num:.1f}GB"

def is_url(text):
    """Matn URL ekanligini tekshirish"""
    url_patterns = [
        r'^https?://(www\.)?youtube\.com/',
        r'^https?://youtu\.be/',
        r'^https?://(www\.)?instagram\.com/',
        r'^https?://(www\.)?tiktok\.com/',
        r'^https?://(www\.)?twitter\.com/',
        r'^https?://(www\.)?x\.com/',
        r'^https?://(www\.)?facebook\.com/',
        r'^https?://(www\.)?soundcloud\.com/',
        r'^https?://(www\.)?vk\.com/',
    ]
    return any(re.match(pattern, text) for pattern in url_patterns)

def detect_platform(url):
    """URL qaysi platformaga tegishli"""
    platforms = {
        'youtube': ['youtube.com', 'youtu.be'],
        'instagram': ['instagram.com'],
        'tiktok': ['tiktok.com'],
        'twitter': ['twitter.com', 'x.com'],
        'facebook': ['facebook.com', 'fb.watch'],
        'soundcloud': ['soundcloud.com'],
        'vk': ['vk.com']
    }
    url_lower = url.lower()
    for platform, domains in platforms.items():
        if any(domain in url_lower for domain in domains):
            return platform
    return 'unknown'

# ==================== YT-DLP SOZLAMALARI ====================
def get_ydl_opts(format_type='audio', progress_hook=None):
    """yt-dlp sozlamalarini qaytarish - COOKIESIZ!"""
    opts = {
        'quiet': True,
        'no_warnings': True,
        'ignoreerrors': True,
        'socket_timeout': TIMEOUT,
        'retries': 5,
        'fragment_retries': 5,
        'extract_flat': False,
        'concurrent_fragment_downloads': 5,
    }
    
    if progress_hook:
        opts['progress_hooks'] = [progress_hook]
    
    if format_type == 'audio':
        opts.update({
            'format': 'bestaudio/best',
            'outtmpl': f'{DOWNLOAD_DIR}/%(id)s.%(ext)s',
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
        })
    else:
        opts.update({
            'format': 'best[ext=mp4]/best',
            'outtmpl': f'{DOWNLOAD_DIR}/%(id)s_%(title).50s.%(ext)s',
            'merge_output_format': 'mp4',
        })
    
    return opts

# ==================== PROGRESS HOOK ====================
class ProgressHook:
    def __init__(self, message, loop):
        self.message = message
        self.loop = loop
        self.last_update = 0
    
    def __call__(self, d):
        if d['status'] == 'downloading':
            now = time.time()
            if now - self.last_update > 3:
                self.last_update = now
                percent = d.get('_percent_str', '0%').strip()
                speed = d.get('_speed_str', '?').strip()
                eta = d.get('_eta_str', '?').strip()
                text = f"⏳ Yuklanmoqda... {percent}\n⚡ Tezlik: {speed}\n⏱ Qolgan vaqt: {eta}"
                asyncio.run_coroutine_threadsafe(
                    self.message.edit_text(text),
                    self.loop
                )

# ==================== ASOSIY KOMANDALAR ====================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/start - Botni ishga tushirish"""
    user = update.effective_user
    welcome_text = f"""
🎵 *Salom {user.first_name}!* 

Musiqa Botiga xush kelibsiz! 🎶

📌 *Men nima qila olaman?*

• 🎤 *Qo'shiq qidirish* - Artist yoki qo'shiq nomini yozing
• 📥 *Havola yuklash* - YouTube, Instagram, TikTok, Twitter havolasini yuboring
• 🎧 *Video tahlil* - Video yuboring, qo'shiq nomini topaman
• 📋 *Katalog* - Qidiruv natijalarini tugmalar bilan chiqaraman

✅ *Hech qanday cookie talab qilinmaydi!*
🚀 *Tez va ishonchli yuklash*

/help - Batafsil yordam
/status - Bot holati
"""
    await update.message.reply_text(welcome_text, parse_mode='Markdown')

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/help - Yordam"""
    help_text = """
📖 *Yordam qo'llanmasi*

1️⃣ *Qo'shiq qidirish*
   • Oddiygina qo'shiq yoki artist nomini yozing
   • Masalan: "Billie Eilish" yoki "Shape of You"
   • Bot 6 ta eng yaxshi natijani ko'rsatadi

2️⃣ *Havola orqali yuklash*
   • YouTube, Instagram, TikTok, Twitter havolasini yuboring
   • Bot avtomatik video yuklaydi
   • Video katta bo'lsa, audio sifatida yuboradi

3️⃣ *Video tahlil (Shazam)*
   • Istalgan video faylni yuboring
   • Bot qo'shiq nomini aniqlaydi
   • Topilgan qo'shiqni yuklab olish mumkin

4️⃣ *Tugmalar*
   • 🎵 Yuklab olish - MP3 formatda
   • 🎬 Video - MP4 formatda
   • 🔍 Qayta qidirish

⚡️ *Maslahat:* Yuklash vaqtida /cancel buyrug'i bilan bekor qiling
"""
    await update.message.reply_text(help_text, parse_mode='Markdown')

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/cancel - Yuklashni bekor qilish"""
    user_id = update.effective_user.id
    if user_tasks.get(user_id, 0) > 0:
        user_tasks[user_id] = 0
        await update.message.reply_text("🛑 Yuklash bekor qilindi!")
    else:
        await update.message.reply_text("ℹ️ Hech qanday faol yuklanish yo'q")

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/status - Bot holati"""
    uptime = int(time.time() - start_time)
    hours, remainder = divmod(uptime, 3600)
    minutes, seconds = divmod(remainder, 60)
    
    # Disk holati
    disk_usage = shutil.disk_usage(DOWNLOAD_DIR)
    free_space = human_size(disk_usage.free)
    
    # Fayllar soni
    files = [f for f in os.listdir(DOWNLOAD_DIR) if os.path.isfile(os.path.join(DOWNLOAD_DIR, f))]
    files_size = sum(os.path.getsize(os.path.join(DOWNLOAD_DIR, f)) for f in files)
    
    status_text = f"""
📊 *Bot Holati*

🤖 *Ish vaqti:* {hours:02d}:{minutes:02d}:{seconds:02d}
⚡ *Faol yuklanishlar:* {sum(user_tasks.values())}
💾 *Saqlangan fayllar:* {len(files)} ta ({human_size(files_size)})
💿 *Bo'sh joy:* {free_space}
🎯 *Maksimum parallel:* {MAX_CONCURRENT}

✅ *FFmpeg:* {"✅ Mavjud" if FFMPEG else "❌ Yo'q"}
🍪 *Cookie:* ❌ Talab qilinmaydi

🚀 *Bot to'liq ishga tayyor!*
"""
    await update.message.reply_text(status_text, parse_mode='Markdown')

# ==================== QOSHIQ QIDIRISH ====================
async def search_music(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Qo'shiq qidirish va katalog chiqarish"""
    query = update.message.text.strip()
    message = await update.message.reply_text(f"🔍 *{query}* qidirilmoqda...", parse_mode='Markdown')
    
    def search():
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': 'in_playlist',
            'noplaylist': True,
            'socket_timeout': 30,
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            return ydl.extract_info(f"ytsearch6:{query}", download=False)
    
    try:
        loop = asyncio.get_event_loop()
        data = await loop.run_in_executor(executor, search)
        
        if not data or 'entries' not in data:
            await message.edit_text("❌ Hech narsa topilmadi. Boshqa so'z bilan urinib ko'ring.")
            return
        
        keyboard = []
        for item in data['entries']:
            if item and item.get('id'):
                title = item.get('title', 'Nomsiz')[:50]
                duration = item.get('duration', 0)
                dur_str = f"{duration // 60}:{duration % 60:02d}" if duration else "??:??"
                
                keyboard.append([
                    InlineKeyboardButton(
                        f"🎵 {title} [{dur_str}]",
                        callback_data=f"audio_{item['id']}"
                    )
                ])
        
        if not keyboard:
            await message.edit_text("❌ Hech qanday natija topilmadi.")
            return
        
        keyboard.append([
            InlineKeyboardButton("🔄 Qayta qidirish", callback_data=f"search_{query[:40]}")
        ])
        
        await message.edit_text(
            f"🎵 *{query}* bo'yicha natijalar:\n👇 Quyidagilardan birini tanlang:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
        
    except Exception as e:
        await message.edit_text(f"❌ Xatolik: {str(e)[:100]}\nQaytadan urinib ko'ring.")

# ==================== YUKLASH FUNKSIYALARI ====================
async def download_audio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Audio yuklash (callback orqali)"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    if user_tasks[user_id] >= MAX_CONCURRENT:
        await query.answer("⚠️ Oldingi yuklash tugasin, biroz kuting!", show_alert=True)
        return
    
    user_tasks[user_id] += 1
    video_id = query.data.split('_')[1]
    url = f"https://youtube.com/watch?v={video_id}"
    
    status_msg = await query.edit_message_text("⏳ Yuklash boshlandi...")
    
    try:
        progress = ProgressHook(status_msg, asyncio.get_event_loop())
        
        def download():
            ydl_opts = get_ydl_opts('audio', progress)
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                return ydl.extract_info(url, download=True)
        
        loop = asyncio.get_event_loop()
        info = await loop.run_in_executor(executor, download)
        
        # MP3 faylni topish
        mp3_file = None
        for f in os.listdir(DOWNLOAD_DIR):
            if f.startswith(video_id) and f.endswith('.mp3'):
                mp3_file = os.path.join(DOWNLOAD_DIR, f)
                break
        
        if not mp3_file or not os.path.exists(mp3_file):
            await status_msg.edit_text("❌ Fayl topilmadi, qaytadan urinib ko'ring.")
            return
        
        # Fayl hajmini tekshirish
        file_size = os.path.getsize(mp3_file)
        if file_size > 50 * 1024 * 1024:
            await status_msg.edit_text(f"⚠️ Fayl juda katta ({human_size(file_size)}), yuklab bo'lmadi.")
            os.remove(mp3_file)
            return
        
        await status_msg.delete()
        
        # Audio yuborish
        with open(mp3_file, 'rb') as f:
            await query.message.reply_audio(
                audio=f,
                title=info.get('title', 'Qo\'shiq')[:200],
                performer=info.get('uploader', 'Artist'),
                caption=f"✅ *{info.get('title', 'Qo\'shiq')[:50]}* yuklab olindi!",
                parse_mode='Markdown'
            )
        
        # Tozalash
        os.remove(mp3_file)
        
    except Exception as e:
        await status_msg.edit_text(f"❌ Yuklashda xatolik: {str(e)[:150]}")
    finally:
        user_tasks[user_id] -= 1

# ==================== VIDEO YUKLASH ====================
async def download_video_url(update: Update, context: ContextTypes.DEFAULT_TYPE, url, audio_only=False):
    """URL orqali video yoki audio yuklash"""
    user_id = update.effective_user.id
    if user_tasks[user_id] >= MAX_CONCURRENT:
        await update.message.reply_text("⚠️ Bir vaqtda faqat 3 tagacha yuklash mumkin. Biroz kuting!")
        return
    
    user_tasks[user_id] += 1
    platform = detect_platform(url)
    msg = await update.message.reply_text(f"⏳ [{platform}] Yuklanmoqda...")
    
    try:
        format_type = 'audio' if audio_only else 'video'
        progress = ProgressHook(msg, asyncio.get_event_loop())
        
        def download():
            ydl_opts = get_ydl_opts(format_type, progress)
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                return ydl.extract_info(url, download=True)
        
        loop = asyncio.get_event_loop()
        info = await loop.run_in_executor(executor, download)
        
        # Faylni topish
        file_ext = 'mp3' if audio_only else 'mp4'
        downloaded_file = None
        for f in os.listdir(DOWNLOAD_DIR):
            if f.endswith(f'.{file_ext}'):
                file_path = os.path.join(DOWNLOAD_DIR, f)
                if os.path.getctime(file_path) > time.time() - 10:
                    downloaded_file = file_path
                    break
        
        if not downloaded_file:
            await msg.edit_text("❌ Yuklash muvaffaqiyatsiz tugadi.")
            return
        
        file_size = os.path.getsize(downloaded_file)
        title = info.get('title', 'Media')[:100]
        
        await msg.delete()
        
        if audio_only:
            with open(downloaded_file, 'rb') as f:
                await update.message.reply_audio(
                    audio=f,
                    title=title,
                    performer=info.get('uploader', ''),
                    caption=f"✅ *{title[:50]}*"
                )
        else:
            with open(downloaded_file, 'rb') as f:
                await update.message.reply_video(
                    video=f,
                    caption=f"✅ *{title[:50]}*",
                    supports_streaming=True
                )
        
        os.remove(downloaded_file)
        
    except Exception as e:
        await msg.edit_text(f"❌ Xatolik: {str(e)[:150]}")
    finally:
        user_tasks[user_id] -= 1

# ==================== SHAZAM (VIDEO TAHIL) ====================
async def analyze_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Yuborilgan videodan qo'shiq nomini aniqlash"""
    video = update.message.video
    if not video:
        await update.message.reply_text("❌ Iltimos, video fayl yuboring!")
        return
    
    if video.file_size > 25 * 1024 * 1024:
        await update.message.reply_text("❌ Video hajmi 25MB dan kichik bo'lishi kerak!")
        return
    
    msg = await update.message.reply_text("🎧 Video tahlil qilinmoqda...")
    
    # Videoni yuklab olish
    video_file = await context.bot.get_file(video.file_id)
    video_path = os.path.join(DOWNLOAD_DIR, f"temp_video_{update.effective_user.id}.mp4")
    await video_file.download_to_drive(video_path)
    
    # Audio ajratish (30 sekund)
    audio_path = os.path.join(DOWNLOAD_DIR, f"temp_audio_{update.effective_user.id}.mp3")
    
    if FFMPEG:
        cmd = f"{FFMPEG} -i {video_path} -t 30 -vn -acodec libmp3lame {audio_path} -y"
        proc = await asyncio.create_subprocess_shell(cmd, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
        await proc.wait()
    else:
        await msg.edit_text("❌ FFmpeg topilmadi, audio ajratib bo'lmadi!")
        return
    
    # Shazam orqali aniqlash
    try:
        from shazamio import Shazam
        
        shazam = Shazam()
        result = await shazam.recognize(audio_path)
        
        if result and 'track' in result:
            track = result['track']
            title = track.get('title', 'Noma\'lum')
            artist = track.get('subtitle', 'Noma\'lum ijrochi')
            
            keyboard = InlineKeyboardMarkup([[
                InlineKeyboardButton("🎵 Qidirish", callback_data=f"search_{title} {artist}"),
                InlineKeyboardButton("🔍 YouTube", url=f"https://youtube.com/results?search_query={title}+{artist}")
            ]])
            
            await msg.delete()
            await update.message.reply_text(
                f"🎵 *Topildi!*\n\n"
                f"📌 *Qo'shiq:* {title}\n"
                f"👤 *Ijrochi:* {artist}\n\n"
                f"👇 Qidirish yoki yuklash uchun tugmalardan foydalaning:",
                reply_markup=keyboard,
                parse_mode='Markdown'
            )
        else:
            await msg.edit_text("❌ Qo'shiq aniqlanmadi. Boshqa video yuboring!")
            
    except ImportError:
        await msg.edit_text("❌ Shazam o'rnatilmagan!")
    except Exception as e:
        await msg.edit_text(f"❌ Tahlil xatosi: {str(e)[:100]}")
    
    # Tozalash
    for f in [video_path, audio_path]:
        if os.path.exists(f):
            os.remove(f)

# ==================== QAYTA QIDIRISH ====================
async def re_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Qayta qidirish"""
    query = update.callback_query
    await query.answer()
    search_query = query.data.split('_')[1]
    
    # Yangi qidiruv xabari
    fake_update = type('obj', (object,), {
        'message': type('obj', (object,), {
            'reply_text': lambda self, text: query.message.reply_text(text),
            'text': search_query
        })
    })()
    
    await search_music(fake_update, context)

# ==================== XABARLARNI QAYTA ISHLASH ====================
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Kiruvchi xabarlarni qayta ishlash"""
    text = update.message.text.strip()
    
    # Audio/video yuklash (havola + audio)
    if text.lower().endswith(' audio') and is_url(text[:-6]):
        url = text[:-6].strip()
        await download_video_url(update, context, url, audio_only=True)
        return
    
    # Faqat havola
    if is_url(text):
        await download_video_url(update, context, text, audio_only=False)
        return
    
    # Qo'shiq qidirish
    await search_music(update, context)

# ==================== BOTNI ISHGA TUSHIRISH ====================
def main():
    """Botni ishga tushirish"""
    print("🎵 Bot ishga tushmoqda...")
    print(f"📁 Yuklash papkasi: {DOWNLOAD_DIR}")
    print(f"🎯 Maksimum parallel yuklash: {MAX_CONCURRENT}")
    print(f"✅ FFmpeg: {'Mavjud' if FFMPEG else 'Yo\\'q'}")
    print(f"🍪 Cookie: TALAB QILINMAYDI")
    print("=" * 50)
    
    app = Application.builder().token(TOKEN).build()
    
    # Komandalar
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("cancel", cancel))
    app.add_handler(CommandHandler("status", status))
    
    # Callbacklar
    app.add_handler(CallbackQueryHandler(download_audio, pattern="^audio_"))
    app.add_handler(CallbackQueryHandler(re_search, pattern="^search_"))
    
    # Media handlerlar
    app.add_handler(MessageHandler(filters.VIDEO, analyze_video))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    print("✅ Bot ishga tushdi! Telegram orqali foydalaning.")
    app.run_polling()

if __name__ == "__main__":
    main()
