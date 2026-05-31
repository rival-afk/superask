# Super ASK (SA)

 AI-агент для удалённого управления ПК через Telegram.

**Основан на [opencode](https://github.com/anomalyco/opencode)** — использует те же 13 инструментов (shell, read, write, edit, glob, grep, webfetch, websearch, task, question, todowrite, apply_patch, skill) и AI-модель через opencode/zen.

## Описание

Super ASK базируется на наборе инструментов [opencode](https://github.com/anomalyco/opencode.git) со следующими изменениями:

- Отсутствует графическая оболочка.
- Добавлен Telegram-бот и SUA (sudo).
- Управление только через Telegram.
- Функция запуска вместе с ядром удалена.

## Компоненты

### Super ASK (SA)
Основной модуль, реализующий набор инструментов по структуре opencode (`packages/opencode/src/tool/`):
- `shell` — выполнение команд в терминале
- `read` — чтение файлов
- `write` — запись файлов
- `glob` — поиск файлов по шаблону
- `grep` — поиск текста в файлах
- `edit` — замена текста в файлах

### SUA (Sudo Manager)
Вспомогательная программа для управления правами `sudo`.  
Автор: [rival-afk/terminal-utils](https://github.com/rival-afk/terminal-utils)

SUA безопасно хранит пароль от `sudo`, который задаётся в боте командой `/sua <password>`.

### Telegram-бот
Точка управления Super ASK. Принимает команды только от администратора.

## Команды бота

| Команда | Аргументы | Описание |
|---------|-----------|----------|
| `/test` | — | Проверка работы нейросети и доступ к sudo |
| `/on` | — | Включить Super ASK |
| `/off` | — | Выключить Super ASK |
| `/offc` | — | Отключить SA в текущей сессии |
| `/offall` | — | Отключить SA навсегда |
| `/sua <password>` | пароль | Сохранить пароль sudo |
| `/sua` | — | Права sudo без подтверждения |
| `/suaoff` | — | Отозвать права sudo |
| `/suaon` | — | Выдать права sudo |
| `/stop` | — | Остановить активный процесс |

### Команды настройки

| Команда | Параметры | Назначение |
|---------|-----------|------------|
| `/SA userid <tg_id>` | Telegram ID | Смена владельца бота |
| `/SA bot <token>` | токен | Смена токена Telegram-бота |
| `/SA model <op> <api> <model>` | оператор/api/модель | Смена модели |

## Установка

```bash
# Клонирование
git clone https://github.com/youcapybara228-svg/superask.git
cd superask

# Установка зависимостей
pip install -r requirements.txt

# Настройка
python run.py --setup

# Запуск
python run.py
```

## Структура проекта

```
superask/
├── agent.md           # Правила для агента
├── run.py             # Точка входа
├── requirements.txt   # Зависимости Python
├── core/
│   ├── config.py      # Управление конфигурацией
│   ├── tools.py       # Инструменты (структура opencode)
│   └── superask.py    # Основная логика
├── bot/
│   └── bot.py         # Telegram-бот
├── sua/
│   ├── sua.py         # SUA (управление sudo)
│   └── sua_socket.py  # Прокси для SUA-бинарника
└── tools/             # Пользовательские инструменты
```

## Ссылки

- [opencode — структура инструментов](https://github.com/anomalyco/opencode.git)
- [terminal-utils — автор SUA](https://github.com/rival-afk/terminal-utils)
- [Репозиторий Super ASK](https://github.com/youcapybara228-svg/superask.git)
