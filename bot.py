import asyncio
import logging
import re
import os
import json
from io import BytesIO

import requests
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import BufferedInputFile
from bs4 import BeautifulSoup

# ===================== КОНФИГ =====================
CONFIG_FILE = "config.json"

if not os.path.exists(CONFIG_FILE):
    print("❌ Файл config.json не найден! Запусти install.sh или создай файл вручную.")
    exit(1)

with open(CONFIG_FILE, "r", encoding="utf-8") as f:
    config = json.load(f)

TOKEN = config.get("TOKEN")
OWNER_ID = int(config.get("OWNER_ID", 0))

if not TOKEN or OWNER_ID == 0:
    print("❌ В config.json отсутствует TOKEN или OWNER_ID")
    exit(1)

# ===================== НАСТРОЙКИ =====================
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36"
}

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

bot = Bot(token=TOKEN, parse_mode="HTML")
dp = Dispatcher()

processing = False


# ===================== ПАРСИНГ ФУНКЦИИ =====================
def get_all_gallery_pages(base_url: str) -> list[str]:
    base_url = re.sub(r'\?p=\d+', '', base_url).rstrip('/')
    try:
        r = requests.get(base_url, headers=HEADERS, timeout=15)
        r.raise_for_status()
    except Exception as e:
        logger.error(f"Не удалось загрузить базовую страницу: {e}")
        return [base_url]

    soup = BeautifulSoup(r.text, "html.parser")
    ptt = soup.find(class_="ptt")
    if not ptt:
        return [base_url]

    page_numbers = []
    for a in ptt.find_all("a"):
        text = a.get_text(strip=True)
        if text.isdigit():
            page_numbers.append(int(text))

    if not page_numbers:
        return [base_url]

    max_page = max(page_numbers) - 1
    pages = [base_url]
    for p in range(1, max_page + 1):
        pages.append(f"{base_url}/?p={p}")
    return pages


def get_image_page_urls(gallery_page_url: str) -> list[str]:
    try:
        r = requests.get(gallery_page_url, headers=HEADERS, timeout=15)
        r.raise_for_status()
    except Exception:
        return []
    soup = BeautifulSoup(r.text, "html.parser")
    urls = []
    for div in soup.find_all("div", class_="gdtm"):
        a = div.find("a")
        if a and a.get("href"):
            urls.append(a["href"])
    return urls


def get_full_image_url(image_page_url: str) -> str | None:
    try:
        r = requests.get(image_page_url, headers=HEADERS, timeout=15)
        r.raise_for_status()
    except Exception:
        return None
    soup = BeautifulSoup(r.text, "html.parser")
    img = soup.find("img", id="img")
    return img["src"] if img and img.get("src") else None


def download_image(img_url: str) -> bytes:
    r = requests.get(img_url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    return r.content


# ===================== ОСНОВНАЯ ЛОГИКА =====================
async def process_gallery(message: types.Message, gallery_url: str):
    global processing
    processing = True
    try:
        await message.answer("🔍 <b>Нахожу страницы галереи...</b>")
        gallery_pages = get_all_gallery_pages(gallery_url)
        await message.answer(f"📄 <b>Найдено страниц:</b> {len(gallery_pages)}")

        await message.answer("🔎 Собираю ссылки на изображения...")
        all_image_pages: list[str] = []
        for page_url in gallery_pages:
            pages = get_image_page_urls(page_url)
            all_image_pages.extend(pages)
            await asyncio.sleep(1.2)

        if not all_image_pages:
            await message.answer("❌ Не найдено ни одного изображения.")
            return

        await message.answer(f"📥 <b>Найдено изображений:</b> {len(all_image_pages)}")

        for i, img_page_url in enumerate(all_image_pages, 1):
            await message.answer(f"📸 Скачиваю фото <b>{i}/{len(all_image_pages)}</b>...")
            full_url = get_full_image_url(img_page_url)
            if not full_url:
                await message.answer(f"⚠️ Пропущено фото {i}")
                await asyncio.sleep(1.5)
                continue

            try:
                content = await asyncio.to_thread(download_image, full_url)
                file = BufferedInputFile(content, filename=f"image_{i}.jpg")

                if len(content) > 10 * 1024 * 1024:
                    await bot.send_document(message.chat.id, file, caption=f"Фото {i}")
                else:
                    await bot.send_photo(message.chat.id, file)
            except Exception as e:
                logger.error(f"Ошибка с фото {i}: {e}")
                await message.answer(f"⚠️ Ошибка с фото {i}")

            await asyncio.sleep(1.5)

        await message.answer("✅ <b>Все изображения отправлены!</b>")
    except Exception as e:
        logger.exception("Критическая ошибка")
        await message.answer(f"❌ Ошибка: {str(e)[:300]}")
    finally:
        processing = False


# ===================== ХЭНДЛЕРЫ =====================
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    if message.from_user.id != OWNER_ID:
        await message.answer("⛔ Доступ только владельцу.")
        return
    await message.answer(
        "👋 <b>E-Hentai Downloader Bot</b>\n\n"
        "Отправь ссылку на галерею вида:\n"
        "<code>https://e-hentai.org/g/3870971/c777572e4c/</code>"
    )


@dp.message(lambda m: m.text and "e-hentai.org/g/" in m.text)
async def handle_link(message: types.Message):
    if message.from_user.id != OWNER_ID:
        await message.answer("⛔ Доступ только владельцу.")
        return
    if processing:
        await message.answer("⏳ Уже обрабатываю галерею, подожди...")
        return

    match = re.search(r'https?://e-hentai\.org/g/\d+/[a-f0-9]+/?', message.text)
    if not match:
        await message.answer("❌ Не удалось распознать ссылку.")
        return

    await process_gallery(message, match.group(0))


# ===================== ЗАПУСК =====================
async def main():
    logger.info("Бот запущен")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Бот остановлен")
    except Exception as e:
        logger.critical(f"Ошибка: {e}")