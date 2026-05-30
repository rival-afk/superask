#!/bin/bash
set -e

echo "=== Установка Super ASK ==="

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
INSTALL_DIR="/opt/superask"
BIN_LINK="/usr/local/bin/superask"
VENV_DIR="$INSTALL_DIR/.venv"

# 1. Копируем проект в /opt/superask
echo "[1/5] Копирование проекта в $INSTALL_DIR..."
sudo mkdir -p "$INSTALL_DIR"
sudo cp -r "$PROJECT_DIR"/* "$PROJECT_DIR"/.* "$INSTALL_DIR/" 2>/dev/null || true
sudo cp -r "$PROJECT_DIR"/.env "$INSTALL_DIR/" 2>/dev/null || true
sudo find "$INSTALL_DIR" -name ".git" -prune -exec rm -rf {} \; 2>/dev/null || true

# 2. Создаём виртуальное окружение
echo "[2/5] Создание виртуального окружения..."
sudo "$(command -v python3)" -m venv "$VENV_DIR"
sudo "$VENV_DIR/bin/pip" install --upgrade pip -q
sudo "$VENV_DIR/bin/pip" install -r "$INSTALL_DIR/requirements.txt" -q

# 3. Устанавливаем symlink в PATH
echo "[3/5] Установка symlink: $BIN_LINK → $INSTALL_DIR/cli.py..."
sudo ln -sf "$INSTALL_DIR/cli.py" "$BIN_LINK"
sudo chmod +x "$INSTALL_DIR/cli.py"

# 4. Фиксим shebang в cli.py на venv python
echo "[4/5] Настройка shebang..."
sudo sed -i "1s|.*|#!$VENV_DIR/bin/python3|" "$INSTALL_DIR/cli.py"

# 5. Настраиваем systemd сервис
echo "[5/5] Установка systemd сервиса..."
sudo cp "$INSTALL_DIR/superask.service" /etc/systemd/system/superask.service
sudo sed -i "s|WorkingDirectory=.*|WorkingDirectory=$INSTALL_DIR|" /etc/systemd/system/superask.service
sudo sed -i "s|ExecStart=.*|ExecStart=$INSTALL_DIR/cli.py|" /etc/systemd/system/superask.service
sudo systemctl daemon-reload
sudo systemctl enable superask.service 2>/dev/null || true

echo ""
echo "=== Установка завершена ==="
echo ""
echo "Команды:"
echo "  superask bot <token>      — Установить токен бота"
echo "  superask userid <id>      — Установить ID администратора"
echo "  superask status           — Статус системы"
echo "  superask start            — Запустить бота (foreground)"
echo "  superask restart          — Перезапустить сервис"
echo "  superask logs             — Логи сервиса"
echo "  superask wol              — Информация о Wake-on-LAN"
echo "  superask tools            — Список инструментов"
echo ""
echo "После установки токена:"
echo "  superask restart"
echo ""
echo "Wake-on-LAN уже включён на enp2s0."
echo "Для отправки magic packet: wakeonlan 8c:16:45:ff:40:15"
