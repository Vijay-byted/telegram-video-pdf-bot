
import os
import re
import asyncio
import logging
import tempfile
from pathlib import Path
from urllib.parse import urlparse

import aiohttp
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHANNEL_ID = os.getenv("CHANNEL_ID")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s"
)

running = False
stop_requested = False

async def download_file(url, path):
    timeout = aiohttp.ClientTimeout(total=3600)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.get(url) as response:
            response.raise_for_status()
            with open(path, "wb") as file:
                async for chunk in response.content.iter_chunked(1024 * 1024):
                    file.write(chunk)

def read_pairs(text):
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    pairs = []
    current_video = None

    for line in lines:
        match = re.search(r"https?://\S+", line)
        if not match:
            continue

        url = match.group(0).rstrip("),]")
        title = line[:match.start()].strip(" :-|")

        if "youtube.com" in url or "youtu.be" in url:
            continue

        if "PDF" in title.upper():
            if current_video:
                pairs.append((current_video, (title, url)))
                current_video = None
        else:
            if current_video:
                pairs.append((current_video, None))
            current_video = (title, url)

    if current_video:
        pairs.append((current_video, None))

    return pairs

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Bot चालू है। अपनी TXT फाइल भेजें।"
    )

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Bot अभी काम कर रहा है।" if running else "Bot अभी खाली है।"
    )

async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global stop_requested
    stop_requested = True
    await update.message.reply_text("रोकने का अनुरोध मिल गया है।")

async def handle_txt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global running, stop_requested

    if running:
        await update.message.reply_text("पहले से एक फाइल प्रोसेस हो रही है।")
        return

    if not update.message.document.file_name.lower().endswith(".txt"):
        await update.message.reply_text("कृपया TXT फाइल भेजें।")
        return

    running = True
    stop_requested = False

    try:
        tg_file = await update.message.document.get_file()

        with tempfile.TemporaryDirectory() as temp_dir:
            txt_path = Path(temp_dir) / "input.txt"
            await tg_file.download_to_drive(txt_path)

            content = txt_path.read_text(encoding="utf-8-sig", errors="replace")
            pairs = read_pairs(content)

            await update.message.reply_text(
                f"{len(pairs)} वीडियो/PDF जोड़े मिले। प्रोसेसिंग शुरू है।"
            )

            for index, (video, pdf) in enumerate(pairs, 1):
                if stop_requested:
                    break

                for item, kind in ((video, "video"), (pdf, "pdf")):
                    if not item or stop_requested:
                        continue

                    title, url = item

                    try:
                        suffix = ".pdf" if kind == "pdf" else ".mp4"
                        path = Path(temp_dir) / f"{index}_{kind}{suffix}"

                        await download_file(url, path)

                        caption = title[:900] if title else f"Class {index}"

                        with open(path, "rb") as media:
                            if kind == "pdf":
                                await context.bot.send_document(
                                    chat_id=CHANNEL_ID,
                                    document=media,
                                    caption=caption
                                )
                            else:
                                await context.bot.send_video(
                                    chat_id=CHANNEL_ID,
                                    video=media,
                                    caption=caption,
                                    supports_streaming=True
                                )

                    except Exception:
                        logging.exception("Media processing failed")
                        await update.message.reply_text(
                            f"क्लास {index} का {kind} भेजने में समस्या हुई।"
                        )

            await update.message.reply_text(
                "प्रोसेसिंग रोक दी गई।" if stop_requested
                else "सभी उपलब्ध लिंक प्रोसेस हो गए।"
            )

    except Exception:
        logging.exception("TXT processing failed")
        await update.message.reply_text("TXT फाइल प्रोसेस नहीं हो सकी।")
    finally:
        running = False
        stop_requested = False

def main():
    if not BOT_TOKEN or not CHANNEL_ID:
        raise RuntimeError("BOT_TOKEN और CHANNEL_ID सेट करें।")

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("stop", stop))
    app.add_handler(
        MessageHandler(filters.Document.ALL, handle_txt)
    )

    app.run_polling()

if __name__ == "__main__":
    main()
                      
