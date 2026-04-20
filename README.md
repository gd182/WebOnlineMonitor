<h1 align="center">WebOnlineMonitor</h1>

<p align="center">
  Веб-приложение для мониторинга онлайн-активности пользователей
</p>

###

<div align="center">
  <img src="https://skillicons.dev/icons?i=py" height="40" alt="python logo" />
  <img width="12" />
  <img src="https://skillicons.dev/icons?i=html" height="40" alt="html logo" />
  <img width="12" />
  <img src="https://skillicons.dev/icons?i=css" height="40" alt="css logo" />
  <img width="12" />
  <img src="https://skillicons.dev/icons?i=js" height="40" alt="javascript logo" />
  <img width="12" />
  <img src="https://skillicons.dev/icons?i=postgres" height="40" alt="postgresql logo" />
  <img width="12" />
  <img src="https://skillicons.dev/icons?i=git" height="40" alt="git logo" />
</div>

###

## О проекте

**WebOnlineMonitor** — веб-сервис на Flask для отслеживания и анализа онлайн-активности пользователей. Приложение собирает события активности, хранит их в PostgreSQL и предоставляет удобный интерфейс для просмотра статистики, фильтрации логов и визуализации данных.

## Возможности

- **Дашборд** — сводная статистика за день / неделю / месяц, графики активности по часам и дням недели, топ пользователей и разбивка по платформам
- **Логи активности** — таблица событий с фильтрацией по дате и пользователям, сохранение фильтров между сессиями
- **Timeline** — визуальная временная шкала активности нескольких пользователей одновременно
- **Управление пользователями** — добавление/удаление отслеживаемых VK-аккаунтов, назначение типов и цветов
- **Интервалы опроса** — гибкая настройка частоты проверки в зависимости от времени простоя
- **Экспорт CSV** — выгрузка событий с фильтрацией по датам и пользователям
- **Административная панель** — управление учётными записями системы, сброс паролей, управление правами

## Стек технологий

| Компонент | Технология |
|-----------|-----------|
| Backend | Python 3, Flask |
| База данных | PostgreSQL + psycopg2 |
| Frontend | Jinja2, Bootstrap, Chart.js |
| Аутентификация | Flask session + Werkzeug |
| Часовые пояса | pytz (Europe/Moscow) |
| WSGI | Gunicorn (wsgi.py) |

## Структура проекта

```
WebOnlineMonitor/
├── app.py              # Flask-приложение, все маршруты
├── wsgi.py             # Точка входа для Gunicorn
├── templates/
│   ├── base.html       # Базовый шаблон с навигацией
│   ├── login.html      # Страница входа
│   ├── dashboard.html  # Главный дашборд
│   ├── logs.html       # Журнал событий
│   ├── timeline.html   # Временная шкала
│   ├── watched_users.html  # Список отслеживаемых
│   ├── user_detail.html    # Детальная страница пользователя
│   ├── intervals.html      # Настройка интервалов
│   └── admin_users.html    # Панель администратора
└── update.sh           # Скрипт обновления и перезапуска сервиса
```

## Установка и запуск

### Требования

- Python 3.9+
- PostgreSQL 13+

### 1. Клонирование репозитория

```bash
git clone <repo-url>
cd WebOnlineMonitor
```

### 2. Создание виртуального окружения

```bash
python3 -m venv venv
source venv/bin/activate
pip install flask psycopg2-binary pytz werkzeug gunicorn
```

### 3. Настройка базы данных

В `app.py` укажите строку подключения к своей БД:

```python
DB_DSN = "postgresql://user:password@127.0.0.1:5432/dbname"
```

### 4. Запуск для разработки

```bash
python app.py
```

### 5. Запуск через Gunicorn (продакшн)

```bash
gunicorn --bind 0.0.0.0:5000 wsgi:app
```

## Деплой как systemd-сервис

Создайте файл `/etc/systemd/system/webmonitor.service`:

```ini
[Unit]
Description=WebOnlineMonitor Flask App
After=network.target postgresql.service

[Service]
User=www-data
WorkingDirectory=/opt/WebOnlineMonitor
ExecStart=/opt/WebOnlineMonitor/venv/bin/gunicorn --bind 127.0.0.1:5000 wsgi:app
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Затем:

```bash
systemctl daemon-reload
systemctl enable webmonitor
systemctl start webmonitor
```

Для обновления приложения используйте скрипт `update.sh`:

```bash
chmod +x update.sh
./update.sh
```

## Таблицы базы данных

| Таблица | Назначение |
|---------|-----------|
| `app_users` | Учётные записи системы (логин, пароль, роль) |
| `watched_users` | Отслеживаемые VK-аккаунты |
| `activity_events` | Журнал событий активности |
| `platforms` | Справочник платформ (web, mobile, etc.) |
| `tracking_intervals` | Правила интервалов опроса по типу пользователя |
| `user_vk_colors` | Персональные цвета пользователей для отображения |

## Маршруты API

| Маршрут | Описание |
|---------|---------|
| `/` | Редирект на дашборд или логин |
| `/login` | Вход в систему |
| `/dashboard` | Главный дашборд со статистикой |
| `/logs` | Журнал активности с фильтрами |
| `/timeline` | Временная шкала |
| `/users` | Список отслеживаемых пользователей |
| `/users/<vk_id>` | Детальная страница пользователя |
| `/intervals` | Настройка интервалов опроса |
| `/export/csv` | Экспорт данных в CSV |
| `/admin/users` | Панель администратора |
