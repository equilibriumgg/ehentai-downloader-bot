#!/bin/bash
set -e

echo "🚀 Установка E-Hentai Telegram Bot..."

sudo apt update && sudo apt upgrade -y
sudo apt install -y python3 python3-venv python3-pip git

BOT_DIR="$HOME/ehentai-bot"
if [ -d "$BOT_DIR" ]; then
    echo "Обновляем существующий бот..."
    cd "$BOT_DIR"
    git pull
else
    echo "Клонируем репозиторий..."
    git clone https://github.com/equilibriumgg/ehentai-downloader-bot.git "$BOT_DIR"
    cd "$BOT_DIR"
fi

python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

if [ ! -f config.json ]; then
    cat > config.json << EOF
{
    "TOKEN": "YOUR_BOT_TOKEN_HERE",
    "OWNER_ID": 123456789
}
EOF
    echo "✅ config.json создан. Открываю редактор..."
    sleep 2
    nano config.json
fi

SERVICE_FILE="/etc/systemd/system/ehbot.service"
sudo tee $SERVICE_FILE > /dev/null << EOF
[Unit]
Description=E-Hentai Telegram Bot
After=network.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$BOT_DIR
ExecStart=$BOT_DIR/venv/bin/python $BOT_DIR/bot.py
Restart=always
RestartSec=5
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable ehbot
sudo systemctl start ehbot

echo "✅ Установка завершена!"
echo "Статус: sudo systemctl status ehbot"
echo "Логи: journalctl -u ehbot -f"