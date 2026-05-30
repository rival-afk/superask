#!/bin/bash
#
# Установщик Super ASK
# Запуск: bash install.sh
#
set -eo pipefail

# ─────────── Цвета ───────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

fail()  { echo -e "${RED}[ОШИБКА]${NC} $*" >&2; exit 1; }
info()  { echo -e "${CYAN}[INFO]${NC} $*"; }
ok()    { echo -e "${GREEN}[OK]${NC} $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }

# ─────────── Проверка ОС ───────────
check_os() {
    info "Проверка операционной системы..."
    case "$(uname -s)" in
        Linux) ;;
        *) fail "Super ASK поддерживается только на Linux. Текущая ОС: $(uname -s)" ;;
    esac

    if [ ! -f /etc/os-release ]; then
        fail "Файл /etc/os-release не найден. Не удаётся определить ОС."
    fi

    # shellcheck source=/dev/null
    . /etc/os-release 2>/dev/null || true
    OS_NAME="${NAME:-Unknown}"
    OS_VERSION="${VERSION_ID:-rolling}"
    OS_ID="${ID:-linux}"
    info "  ОС: $OS_NAME $OS_VERSION ($OS_ID)"

    case "$OS_ID" in
        arch|archarm|manjaro|endeavour|artix|cachyos|garuda|arcolinux)
            PKG_MANAGER="pacman"
            PYTHON_PKG="python"
            ;;
        ubuntu|debian|pop|linuxmint|elementary|kali)
            PKG_MANAGER="apt"
            PYTHON_PKG="python3"
            ;;
        fedora)
            PKG_MANAGER="dnf"
            PYTHON_PKG="python3"
            ;;
        opensuse*|suse)
            PKG_MANAGER="zypper"
            PYTHON_PKG="python3"
            ;;
        alpine)
            PKG_MANAGER="apk"
            PYTHON_PKG="python3"
            ;;
        *)
            warn "Неизвестный дистрибутив '$OS_ID'. Установка может не сработать."
            PKG_MANAGER=""
            PYTHON_PKG="python3"
            ;;
    esac
    ok "ОС: $NAME, пакетный менеджер: $PKG_MANAGER"
}

# ─────────── Проверка зависимостей ───────────
check_deps() {
    info "Проверка системных зависимостей..."
    local missing=()
    local required=("python3" "sudo" "systemctl" "ethtool")

    for cmd in "${required[@]}"; do
        if ! command -v "$cmd" &>/dev/null; then
            missing+=("$cmd")
        fi
    done

    if [ ${#missing[@]} -gt 0 ]; then
        echo -e "${YELLOW}  Отсутствуют: ${missing[*]}${NC}"
        case "$PKG_MANAGER" in
            pacman)
                info "  Установка: sudo pacman -S ${missing[*]}"
                if ! sudo pacman -S --noconfirm "${missing[@]}" 2>&1; then
                    fail "Не удалось установить зависимости. Установите вручную: sudo pacman -S ${missing[*]}"
                fi
                ;;
            apt)
                info "  Установка: sudo apt install -y ${missing[*]}"
                if ! sudo apt install -y "${missing[@]}" 2>&1; then
                    fail "Не удалось установить зависимости. Установите вручную: sudo apt install -y ${missing[*]}"
                fi
                ;;
            dnf)
                info "  Установка: sudo dnf install -y ${missing[*]}"
                if ! sudo dnf install -y "${missing[@]}" 2>&1; then
                    fail "Не удалось установить зависимости. Установите вручную: sudo dnf install -y ${missing[*]}"
                fi
                ;;
            *)
                warn "  Установите вручную: ${missing[*]}"
                warn "  Пропускаю автоматическую установку зависимостей."
                ;;
        esac
    fi

    # Проверка Python 3
    PYTHON=$(command -v python3)
    if [ -z "$PYTHON" ]; then
        PYTHON=$(command -v python)
    fi
    if [ -z "$PYTHON" ]; then
        fail "Python 3 не найден. Установите: sudo pacman -S python (или аналог для вашего дистрибутива)"
    fi

    pyver=$("$PYTHON" --version 2>&1 | grep -oP '\d+\.\d+')
    py_major=$(echo "$pyver" | cut -d. -f1)
    if [ "$py_major" -lt 3 ]; then
        fail "Требуется Python 3. Установлен: $("$PYTHON" --version)"
    fi
    ok "Python: $("$PYTHON" --version 2>&1)"
    ok "Все системные зависимости найдены"
}

# ─────────── Проверка прав ───────────
check_permissions() {
    info "Проверка прав доступа..."

    if [ "$(id -u)" -eq 0 ]; then
        warn "Запуск от root. Рекомендуется запускать от обычного пользователя."
    fi

    if ! sudo -n true 2>/dev/null; then
        warn "Для некоторых шагов потребуется sudo."
        warn "  Подтвердите пароль в sudo, если потребуется."
        # Пробуем выполнить sudo считывая пароль через терминал
        if ! sudo -v 2>/dev/null; then
            # Если терминал не интерактивный, пытаемся выполнить простую команду
            if ! sudo true 2>/dev/null; then
                fail "Нет прав sudo. Установка невозможна."
            fi
        fi
    fi

    ok "Права доступа: OK"
}

# ─────────── Проверка директории ───────────
check_project_dir() {
    info "Проверка директории проекта..."
    SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

    if [ ! -f "$SCRIPT_DIR/cli.py" ]; then
        fail "Файл cli.py не найден в $SCRIPT_DIR. Запустите скрипт из корня проекта Super ASK."
    fi
    if [ ! -f "$SCRIPT_DIR/requirements.txt" ]; then
        fail "Файл requirements.txt не найден в $SCRIPT_DIR."
    fi
    if [ ! -f "$SCRIPT_DIR/superask.service" ]; then
        warn "Файл superask.service не найден. Сервис systemd не будет установлен."
    fi

    ok "Директория проекта: $SCRIPT_DIR"
    PROJECT_DIR="$SCRIPT_DIR"
}

# ─────────── Фаза 1: копирование ───────────
phase_copy() {
    INSTALL_DIR="/opt/superask"
    info "[1/6] Копирование проекта в $INSTALL_DIR..."

    if sudo mkdir -p "$INSTALL_DIR" 2>/dev/null; then
        ok "  Директория $INSTALL_DIR создана"
    else
        fail "  Не удалось создать $INSTALL_DIR. Проверьте права sudo."
    fi

    sudo cp "$PROJECT_DIR/cli.py" "$INSTALL_DIR/" 2>/dev/null || fail "Не удалось скопировать cli.py"
    sudo cp "$PROJECT_DIR/requirements.txt" "$INSTALL_DIR/" 2>/dev/null || fail "Не удалось скопировать requirements.txt"

    for dir in core bot sua tools skills; do
        if [ -d "$PROJECT_DIR/$dir" ]; then
            sudo mkdir -p "$INSTALL_DIR/$dir"
            sudo cp -r "$PROJECT_DIR/$dir"/* "$INSTALL_DIR/$dir/" 2>/dev/null || true
        fi
    done

    # __init__.py для пакетов (если забыли)
    for dir in core bot sua tools; do
        if [ -d "$INSTALL_DIR/$dir" ]; then
            sudo touch "$INSTALL_DIR/$dir/__init__.py" 2>/dev/null || true
        fi
    done

    # Копируем html-файл с ТЗ (если есть)
    for f in "$PROJECT_DIR"/*.html; do
        [ -f "$f" ] && sudo cp "$f" "$INSTALL_DIR/" 2>/dev/null || true
        break
    done

    # Удаляем .git если попал
    sudo rm -rf "$INSTALL_DIR/.git" 2>/dev/null || true

    # Права
    sudo chown -R "$(whoami):$(id -gn)" "$INSTALL_DIR" 2>/dev/null || true
    sudo chmod -R u+w "$INSTALL_DIR" 2>/dev/null || true

    ok "  Файлы скопированы в $INSTALL_DIR"
}

# ─────────── Фаза 2: виртуальное окружение ───────────
phase_venv() {
    VENV_DIR="$INSTALL_DIR/.venv"
    info "[2/6] Создание виртуального окружения Python..."

    if [ -d "$VENV_DIR" ] && [ -f "$VENV_DIR/bin/python3" ]; then
        warn "  Виртуальное окружение уже существует. Будет пересоздано."
        rm -rf "$VENV_DIR" 2>/dev/null || {
            sudo rm -rf "$VENV_DIR" 2>/dev/null || true
        }
    fi

    if ! "$PYTHON" -m venv "$VENV_DIR" 2>&1; then
        # Попробуем с venv модулем
        if "$PYTHON" -c "import venv" 2>/dev/null; then
            "$PYTHON" -m venv "$VENV_DIR" 2>&1 || fail "Не удалось создать venv"
        else
            warn "  Модуль venv не найден. Установите python-venv:"
            case "$PKG_MANAGER" in
                pacman) warn "    sudo pacman -S python-virtualenv" ;;
                apt)    warn "    sudo apt install -y python3-venv" ;;
                dnf)    warn "    sudo dnf install -y python3-virtualenv" ;;
                *)      warn "    Установите пакет python-virtualenv или python3-venv" ;;
            esac
            fail "Виртуальное окружение не создано."
        fi
    fi
    ok "  Виртуальное окружение: $VENV_DIR"

    info "  Установка pip..."
    if ! "$VENV_DIR/bin/pip" install --upgrade pip -q 2>&1; then
        warn "  Не удалось обновить pip. Продолжаем..."
    fi

    info "  Установка зависимостей из requirements.txt..."
    ATTEMPTS=0
    while [ $ATTEMPTS -lt 3 ]; do
        if "$VENV_DIR/bin/pip" install -r "$INSTALL_DIR/requirements.txt" -q 2>&1; then
            ok "  Зависимости установлены"
            break
        fi
        ATTEMPTS=$((ATTEMPTS + 1))
        if [ $ATTEMPTS -lt 3 ]; then
            warn "  Попытка $ATTEMPTS/3 не удалась. Повтор через 3 сек..."
            sleep 3
        else
            fail "  Не удалось установить зависимости после 3 попыток."
            warn "  Попробуйте вручную: $VENV_DIR/bin/pip install -r $INSTALL_DIR/requirements.txt"
            warn "  Проверьте интернет-соединение: ping -c 3 pypi.org"
        fi
    done
}

# ─────────── Фаза 3: shebang ───────────
phase_shebang() {
    info "[3/6] Настройка интерпретатора..."
    VENV_PYTHON="$VENV_DIR/bin/python3"
    if [ ! -f "$VENV_PYTHON" ]; then
        VENV_PYTHON="$VENV_DIR/bin/python"
    fi
    if [ ! -f "$VENV_PYTHON" ]; then
        fail "Не найден python в виртуальном окружении: $VENV_DIR/bin/"
    fi
    sudo sed -i "1s|^#\!.*|#!$VENV_PYTHON|" "$INSTALL_DIR/cli.py" 2>/dev/null || {
        warn "  Не удалось изменить shebang. Используем стандартный."
    }
    sudo chmod +x "$INSTALL_DIR/cli.py" 2>/dev/null || true
    ok "  Интерпретатор: $VENV_PYTHON"
}

# ─────────── Фаза 4: symlink ───────────
phase_symlink() {
    BIN_LINK="/usr/local/bin/sa"
    info "[4/6] Установка symlink..."

    if [ -L "$BIN_LINK" ] || [ -f "$BIN_LINK" ]; then
        warn "  $BIN_LINK уже существует. Будет перезаписан."
        sudo rm -f "$BIN_LINK" 2>/dev/null || true
    fi

    sudo ln -s "$INSTALL_DIR/cli.py" "$BIN_LINK" 2>/dev/null || {
        fail "Не удалось создать symlink $BIN_LINK. Попробуйте: sudo ln -s $INSTALL_DIR/cli.py $BIN_LINK"
    }

    # Проверка что symlink в PATH
    if ! command -v superask &>/dev/null; then
        warn "  Команда 'superask' не найдена в PATH."
        warn "  Добавьте /usr/local/bin в PATH или используйте полный путь."
        PATH="$PATH:/usr/local/bin"
        export PATH
    fi

    ok "  Команда 'superask' установлена: $BIN_LINK → $INSTALL_DIR/cli.py"
}

# ─────────── Фаза 5: сервис systemd ───────────
phase_service() {
    info "[5/6] Настройка systemd сервиса..."

    SRC_SERVICE="$INSTALL_DIR/superask.service"
    if [ ! -f "$SRC_SERVICE" ]; then
        warn "  Файл superask.service не найден. Пропускаем."
        return
    fi

    DST_SERVICE="/etc/systemd/system/superask.service"

    if [ -f "$DST_SERVICE" ]; then
        warn "  Сервис уже установлен. Будет перезаписан."
        sudo rm -f "$DST_SERVICE" 2>/dev/null || true
    fi

    # Создаём временный файл сервиса
    TMP_SERVICE=$(mktemp)
    cat > "$TMP_SERVICE" << EOF
[Unit]
Description=Super ASK — Telegram bot for remote PC control
After=network.target network-online.target
Wants=network-online.target wakeonlan.service

[Service]
Type=simple
User=$(whoami)
WorkingDirectory=$INSTALL_DIR
ExecStart=$INSTALL_DIR/cli.py
Restart=always
RestartSec=10
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
EOF

    sudo cp "$TMP_SERVICE" "$DST_SERVICE" 2>/dev/null || {
        rm -f "$TMP_SERVICE"
        fail "Не удалось скопировать сервис в $DST_SERVICE"
    }
    rm -f "$TMP_SERVICE"

    sudo systemctl daemon-reload 2>/dev/null || {
        warn "  systemctl daemon-reload не сработал."
    }

    if sudo systemctl enable superask.service 2>/dev/null; then
        ok "  Сервис superask добавлен в автозагрузку"
    else
        warn "  Не удалось включить автозагрузку. Попробуйте: sudo systemctl enable superask"
    fi

    # Проверка сервиса wakeonlan
    if [ -f "/etc/systemd/system/wakeonlan.service" ]; then
        if ! systemctl is-enabled wakeonlan.service &>/dev/null; then
            sudo systemctl enable wakeonlan.service 2>/dev/null || true
        fi
    fi

    ok "  Сервис superask.service установлен"
}

# ─────────── Фаза 6: Wake-on-LAN ───────────
phase_wol() {
    info "[6/6] Настройка Wake-on-LAN..."

    # Ищем ethernet интерфейс
    ETH_IFACE=""
    for iface in /sys/class/net/*; do
        name=$(basename "$iface")
        # Пропускаем lo, wl*, virbr*, docker*
        case "$name" in
            lo|wl*|virbr*|docker*|br-*|veth*) continue ;;
        esac
        if [ -d "$iface" ]; then
            ETH_IFACE="$name"
            break
        fi
    done

    if [ -z "$ETH_IFACE" ]; then
        warn "  Ethernet-интерфейс не найден."
        warn "  Wake-on-LAN не настроен. Настройте вручную:"
        warn "    sudo ethtool -s <интерфейс> wol g"
        return
    fi

    MAC=$(cat "/sys/class/net/$ETH_IFACE/address" 2>/dev/null || echo "unknown")

    if ! command -v ethtool &>/dev/null; then
        warn "  ethtool не установлен. Wake-on-LAN не настроен."
        return
    fi

    if ! sudo ethtool -s "$ETH_IFACE" wol g 2>/dev/null; then
        warn "  Не удалось включить WoL на $ETH_IFACE."
        return
    fi

    # Создаём сервис для WoL
    WOL_SERVICE="/etc/systemd/system/wakeonlan.service"
    TMP_WOL=$(mktemp)
    cat > "$TMP_WOL" << EOF
[Unit]
Description=Enable Wake-on-LAN on $ETH_IFACE
Requires=network.target
After=network.target

[Service]
Type=oneshot
ExecStart=/usr/bin/ethtool -s $ETH_IFACE wol g
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
EOF

    if [ -f "$WOL_SERVICE" ]; then
        sudo cp "$TMP_WOL" "$WOL_SERVICE" 2>/dev/null || true
    else
        sudo cp "$TMP_WOL" "$WOL_SERVICE" 2>/dev/null || true
    fi
    rm -f "$TMP_WOL"

    sudo systemctl daemon-reload 2>/dev/null || true
    sudo systemctl enable wakeonlan.service 2>/dev/null || true
    sudo systemctl restart wakeonlan.service 2>/dev/null || true

    # Проверка
    if sudo ethtool "$ETH_IFACE" 2>/dev/null | grep -q "Wake-on: g"; then
        ok "  Wake-on-LAN включён на $ETH_IFACE (MAC: $MAC)"
    else
        warn "  WoL не удалось включить. Проверьте: sudo ethtool -s $ETH_IFACE wol g"
    fi

    # Устанавливаем wakeonlan если есть
    if ! command -v wakeonlan &>/dev/null; then
        case "$PKG_MANAGER" in
            pacman)
                info "  Установка wakeonlan..."
                sudo pacman -S --noconfirm wakeonlan 2>/dev/null || true
                ;;
            apt)
                info "  Установка wakeonlan..."
                sudo apt install -y wakeonlan 2>/dev/null || true
                ;;
            *) ;;
        esac
    fi

    if command -v wakeonlan &>/dev/null; then
        ok "  wakeonlan установлен. Отправка: wakeonlan $MAC"
    fi
}

# ─────────── Финал ───────────
final_check() {
    info "Проверка установки..."
    local errors=0

    if [ ! -f "$INSTALL_DIR/cli.py" ]; then
        echo -e "${RED}  ✗ cli.py не найден${NC}" >&2
        errors=$((errors + 1))
    else
        echo -e "${GREEN}  ✓ cli.py${NC}"
    fi

    if [ -L "$BIN_LINK" ]; then
        echo -e "${GREEN}  ✓ superask в PATH${NC}"
    else
        echo -e "${RED}  ✗ superask не в PATH${NC}" >&2
        errors=$((errors + 1))
    fi

    if [ -f "$VENV_DIR/bin/python3" ] || [ -f "$VENV_DIR/bin/python" ]; then
        echo -e "${GREEN}  ✓ Виртуальное окружение${NC}"
    else
        echo -e "${RED}  ✗ Виртуальное окружение не найдено${NC}" >&2
        errors=$((errors + 1))
    fi

    # Проверка что venv работает
    VENV_PY="$VENV_DIR/bin/python3"
    [ -f "$VENV_PY" ] || VENV_PY="$VENV_DIR/bin/python"
    if [ -f "$VENV_PY" ]; then
        if "$VENV_PY" -c "import telegram" 2>/dev/null; then
            echo -e "${GREEN}  ✓ python-telegram-bot установлен${NC}"
        else
            echo -e "${RED}  ✗ python-telegram-bot не установлен${NC}" >&2
            errors=$((errors + 1))
        fi
    fi

    if [ -f "/etc/systemd/system/superask.service" ]; then
        echo -e "${GREEN}  ✓ Сервис superask${NC}"
    else
        echo -e "${YELLOW}  ~ Сервис superask не установлен${NC}"
    fi

    echo ""
    if [ $errors -eq 0 ]; then
        ok "Установка завершена успешно!"
    else
        warn "Установка завершена с $errors ошибками."
        warn "Проверьте сообщения выше."
    fi
}

# ─────────── Главная функция ───────────
main() {
    echo ""
    echo -e "${CYAN}╔════════════════════════════════════╗${NC}"
    echo -e "${CYAN}║      Super ASK — Установка        ║${NC}"
    echo -e "${CYAN}╚════════════════════════════════════╝${NC}"
    echo ""

    check_os
    echo ""
    check_deps
    echo ""
    check_permissions
    echo ""
    check_project_dir
    echo ""
    echo -e "${CYAN}─── Установка ────────────────────────${NC}"
    echo ""

    phase_copy
    echo ""
    phase_venv
    echo ""
    phase_shebang
    echo ""
    phase_symlink
    echo ""
    phase_service
    echo ""
    phase_wol
    echo ""

    echo -e "${CYAN}─── Проверка ─────────────────────────${NC}"
    echo ""
    final_check

    echo ""
    echo -e "${CYAN}╔════════════════════════════════════╗${NC}"
    echo -e "${CYAN}║       Установка завершена          ║${NC}"
    echo -e "${CYAN}╚════════════════════════════════════╝${NC}"
    echo ""
    echo " Быстрый старт:"
    echo ""
    echo "   1. Установите токен бота:"
    echo -e "      ${GREEN}sa bot 123456789:ABCdef...${NC}"
    echo ""
    echo "   2. Установите ID администратора (опционально):"
    echo -e "      ${GREEN}sa userid <ваш_telegram_id>${NC}"
    echo ""
    echo "   3. Запустите сервис:"
    echo -e "      ${GREEN}sa restart${NC}"
    echo ""
    echo "   4. Проверьте статус:"
    echo -e "      ${GREEN}sa status${NC}"
    echo ""
    echo "   5. Для отправки magic packet WoL:"
    echo -e "      ${GREEN}wakeonlan 8c:16:45:ff:40:15${NC}"
    echo ""
}

main "$@"
