from flask import Flask, render_template, request, redirect, url_for, session, flash, Response
import os
import csv
import io
import json
from functools import wraps
from datetime import datetime
import psycopg2
import psycopg2.extras
import pytz
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
# Секретный ключ генерируется при каждом старте
app.secret_key = os.urandom(24)

# Строка подключения к PostgreSQL
DB_DSN = "postgresql://user:password@ip:port/db"

# Часовой пояс для отображения времени событий
tz_moscow = pytz.timezone('timeZone')


def get_db():
    """Открывает новое соединение с БД. Используется через контекстный менеджер (with get_db())."""
    return psycopg2.connect(DB_DSN)


def login_required(f):
    """Декоратор: требует наличия активной сессии, иначе — редирект на /login."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'username' not in session:
            return redirect(url_for('login', next=request.url))
        return f(*args, **kwargs)
    return decorated_function


def admin_required(f):
    """Декоратор: требует прав администратора, иначе — редирект на дашборд."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'username' not in session:
            return redirect(url_for('login'))
        if not session.get('is_admin'):
            flash('Недостаточно прав', 'danger')
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated_function


@app.route('/')
def home():
    if 'username' not in session:
        return redirect(url_for('login'))
    return redirect(url_for('dashboard'))


@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'username' in session:
        return redirect(url_for('show_logs'))

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')

        with get_db() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("SELECT * FROM app_users WHERE username = %s", (username,))
                user = cur.fetchone()

        if user and check_password_hash(user['password_hash'], password):
            session['username']  = user['username']
            session['user_name'] = user['name']
            session['is_admin']  = user['is_admin']
            session['user_id']   = user['id']
            flash('Вы успешно вошли в систему', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Неверное имя пользователя или пароль', 'danger')

    return render_template('login.html')


@app.route('/logout')
def logout():
    session.clear()
    flash('Вы вышли из системы', 'info')
    return redirect(url_for('login'))


def _load_user_filters(user_id: int) -> dict:
    """Загружает сохранённые фильтры страницы активности из профиля пользователя в БД."""
    with get_db() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT saved_filters FROM app_users WHERE id = %s", (user_id,))
            row = cur.fetchone()
    return (row['saved_filters'] or {}) if row else {}


def _save_user_filters(user_id: int, filters: dict):
    """Сохраняет текущие фильтры страницы активности в профиль пользователя."""
    import json
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE app_users SET saved_filters = %s WHERE id = %s",
                        (json.dumps(filters), user_id))
        conn.commit()


def _load_user_colors(user_id: int) -> dict:
    """Возвращает словарь {user_id: color} для персональной раскраски карточек."""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT vk_id, color FROM user_vk_colors WHERE app_user_id = %s", (user_id,))
            return {row[0]: row[1] for row in cur.fetchall()}


@app.route('/logs')
@login_required
def show_logs():
    user_id = session.get('user_id')
    today   = datetime.now(tz_moscow).strftime("%d.%m.%Y")

    # Параметр reset очищает сохранённые фильтры и перезагружает страницу
    if request.args.get('reset'):
        if user_id:
            _save_user_filters(user_id, {})
        return redirect(url_for('show_logs'))

    # Если фильтры переданы через URL — применяем и сохраняем в профиль
    has_explicit = 'date_from' in request.args or 'vk_ids[]' in request.args
    if has_explicit:
        date_from     = request.args.get('date_from', today)
        date_to       = request.args.get('date_to', today)
        vk_id_filters = request.args.getlist('vk_ids[]')
        if user_id:
            _save_user_filters(user_id, {
                'date_from': date_from,
                'date_to':   date_to,
                'vk_ids':    vk_id_filters,
            })
    else:
        # Явных фильтров нет — берём последние сохранённые из профиля
        saved = _load_user_filters(user_id) if user_id else {}
        date_from     = saved.get('date_from', today)
        date_to       = saved.get('date_to',   today)
        vk_id_filters = saved.get('vk_ids',    [])

    try:
        from_dt = datetime.strptime(date_from, "%d.%m.%Y").replace(hour=0, minute=0, second=0)
        to_dt   = datetime.strptime(date_to,   "%d.%m.%Y").replace(hour=23, minute=59, second=59)
    except ValueError:
        from_dt = to_dt = datetime.now()

    from_dt = tz_moscow.localize(from_dt)
    to_dt   = tz_moscow.localize(to_dt)

    with get_db() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT vk_id, first_name, last_name
                FROM watched_users ORDER BY last_name, first_name
            """)
            watched_users = cur.fetchall()

            query = """
                SELECT ae.vk_id, wu.first_name, wu.last_name,
                       ae.seen_time AT TIME ZONE 'Europe/Moscow' AS seen_time,
                       p.name AS platform
                FROM activity_events ae
                LEFT JOIN watched_users wu ON ae.vk_id = wu.vk_id
                LEFT JOIN platforms p ON ae.platform_id = p.id
                WHERE ae.seen_time >= %s AND ae.seen_time <= %s
            """
            params = [from_dt, to_dt]
            if vk_id_filters:
                query += " AND ae.vk_id = ANY(%s)"
                params.append([int(v) for v in vk_id_filters])
            query += " ORDER BY ae.seen_time DESC"

            cur.execute(query, params)
            entries = cur.fetchall()

    color_map = _load_user_colors(user_id) if user_id else {}

    return render_template('logs.html',
                           entries=entries,
                           watched_users=watched_users,
                           date_from=date_from,
                           date_to=date_to,
                           vk_id_filters=vk_id_filters,
                           color_map=color_map)


@app.route('/users')
@login_required
def watched_users_list():
    with get_db() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT wu.vk_id, wu.first_name, wu.last_name, wu.user_type,
                       COUNT(ae.id) AS event_count,
                       MAX(ae.seen_time) AT TIME ZONE 'Europe/Moscow' AS last_seen
                FROM watched_users wu
                LEFT JOIN activity_events ae ON ae.vk_id = wu.vk_id
                GROUP BY wu.vk_id, wu.first_name, wu.last_name, wu.user_type
                ORDER BY wu.last_name, wu.first_name
            """)
            users = cur.fetchall()
            cur.execute("SELECT DISTINCT user_type FROM tracking_intervals ORDER BY user_type")
            tracked_types = [row['user_type'] for row in cur.fetchall()]
            # Глобальный idle — секунды с последнего события среди всех пользователей
            cur.execute("SELECT EXTRACT(EPOCH FROM (NOW() - MAX(seen_time)))::int FROM activity_events")
            global_idle = cur.fetchone()['extract'] or 0
            # Все правила интервалов
            cur.execute("SELECT user_type, idle_from, idle_to, interval FROM tracking_intervals ORDER BY user_type, idle_from")
            all_intervals = cur.fetchall()

    # Группируем правила интервалов по типу пользователя для быстрого поиска
    intervals_by_type: dict = {}
    for row in all_intervals:
        intervals_by_type.setdefault(row['user_type'], []).append(row)

    def current_interval(user_type):
        """Возвращает текущий интервал опроса для данного типа, исходя из глобального idle."""
        if user_type == 0:
            return None
        for rule in intervals_by_type.get(user_type, []):
            if global_idle >= rule['idle_from'] and (rule['idle_to'] is None or global_idle < rule['idle_to']):
                return rule['interval']
        rules = intervals_by_type.get(user_type)
        return rules[-1]['interval'] if rules else None

    user_id   = session.get('user_id')
    color_map = _load_user_colors(user_id) if user_id else {}

    return render_template('watched_users.html', users=users, tracked_types=tracked_types,
                           current_interval=current_interval, global_idle=global_idle,
                           color_map=color_map)


@app.route('/users/add', methods=['POST'])
@login_required
def add_user():
    vk_id = request.form.get('vk_id', '').strip()
    user_type = request.form.get('user_type', '0').strip()

    if not vk_id.isdigit():
        flash('ID должен быть числом', 'danger')
        return redirect(url_for('watched_users_list'))

    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO watched_users (vk_id, user_type) VALUES (%s, %s) ON CONFLICT (vk_id) DO NOTHING",
                    (int(vk_id), int(user_type))
                )
            conn.commit()
        flash(f'Пользователь {vk_id} добавлен', 'success')
    except Exception as e:
        flash(f'Ошибка: {e}', 'danger')

    return redirect(url_for('watched_users_list'))


@app.route('/users/delete/<int:vk_id>', methods=['POST'])
@login_required
def delete_user(vk_id):
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM watched_users WHERE vk_id = %s", (vk_id,))
            conn.commit()
        flash(f'Пользователь {vk_id} удалён', 'success')
    except Exception as e:
        flash(f'Ошибка: {e}', 'danger')

    return redirect(url_for('watched_users_list'))


@app.route('/users/type/<int:vk_id>', methods=['POST'])
@login_required
def change_user_type(vk_id):
    user_type = request.form.get('user_type', '0')
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE watched_users SET user_type = %s WHERE vk_id = %s",
                    (int(user_type), vk_id)
                )
            conn.commit()
        flash('Тип пользователя обновлён', 'success')
    except Exception as e:
        flash(f'Ошибка: {e}', 'danger')

    return redirect(url_for('watched_users_list'))


# Интервалы опроса 
# Позволяют задавать разную частоту проверки в зависимости от времени простоя

@app.route('/intervals')
@login_required
def intervals_list():
    with get_db() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT id, user_type, idle_from, idle_to, interval
                FROM tracking_intervals
                ORDER BY user_type, idle_from
            """)
            rows = cur.fetchall()
    groups: dict = {}
    for row in rows:
        groups.setdefault(row['user_type'], []).append(row)
    return render_template('intervals.html', groups=groups)


@app.route('/intervals/add', methods=['POST'])
@login_required
def add_interval():
    user_type = request.form.get('user_type', '').strip()
    idle_from  = request.form.get('idle_from', '0').strip()
    idle_to    = request.form.get('idle_to', '').strip() or None
    interval   = request.form.get('interval', '').strip()

    if not user_type.isdigit() or not idle_from.isdigit() or not interval.isdigit():
        flash('Все числовые поля должны быть заполнены', 'danger')
        return redirect(url_for('intervals_list'))
    if int(user_type) == 0:
        flash('Тип 0 — не отслеживается, правила для него не нужны', 'warning')
        return redirect(url_for('intervals_list'))

    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO tracking_intervals (user_type, idle_from, idle_to, interval) VALUES (%s, %s, %s, %s)",
                    (int(user_type), int(idle_from), int(idle_to) if idle_to else None, int(interval))
                )
            conn.commit()
        flash('Правило добавлено', 'success')
    except Exception as e:
        flash(f'Ошибка: {e}', 'danger')

    return redirect(url_for('intervals_list'))


@app.route('/intervals/delete/<int:row_id>', methods=['POST'])
@login_required
def delete_interval(row_id):
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM tracking_intervals WHERE id = %s", (row_id,))
            conn.commit()
        flash('Правило удалено', 'success')
    except Exception as e:
        flash(f'Ошибка: {e}', 'danger')

    return redirect(url_for('intervals_list'))


@app.route('/intervals/edit/<int:row_id>', methods=['POST'])
@login_required
def edit_interval(row_id):
    idle_from = request.form.get('idle_from', '').strip()
    idle_to   = request.form.get('idle_to', '').strip() or None
    interval  = request.form.get('interval', '').strip()

    if not idle_from.isdigit() or not interval.isdigit():
        flash('Некорректные значения', 'danger')
        return redirect(url_for('intervals_list'))

    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE tracking_intervals SET idle_from=%s, idle_to=%s, interval=%s WHERE id=%s",
                    (int(idle_from), int(idle_to) if idle_to else None, int(interval), row_id)
                )
            conn.commit()
        flash('Правило обновлено', 'success')
    except Exception as e:
        flash(f'Ошибка: {e}', 'danger')

    return redirect(url_for('intervals_list'))


# Dashboard
# Главная страница с агрегированной статистикой и графиками

@app.route('/dashboard')
@login_required
def dashboard():
    with get_db() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT COUNT(*) AS cnt FROM activity_events WHERE seen_time >= NOW()::date")
            today_count = cur.fetchone()['cnt']

            cur.execute("SELECT COUNT(*) AS cnt FROM activity_events WHERE seen_time >= date_trunc('week', NOW())")
            week_count = cur.fetchone()['cnt']

            cur.execute("SELECT COUNT(*) AS cnt FROM activity_events WHERE seen_time >= date_trunc('month', NOW())")
            month_count = cur.fetchone()['cnt']

            cur.execute("SELECT COUNT(*) AS cnt FROM activity_events")
            total_count = cur.fetchone()['cnt']

            cur.execute("""
                SELECT EXTRACT(HOUR FROM seen_time AT TIME ZONE 'Europe/Moscow')::int AS hour, COUNT(*) AS cnt
                FROM activity_events GROUP BY hour ORDER BY hour
            """)
            by_hour_raw = {row['hour']: row['cnt'] for row in cur.fetchall()}
            by_hour = [by_hour_raw.get(h, 0) for h in range(24)]

            cur.execute("""
                SELECT DATE(seen_time AT TIME ZONE 'Europe/Moscow') AS day, COUNT(*) AS cnt
                FROM activity_events WHERE seen_time >= NOW() - INTERVAL '30 days'
                GROUP BY day ORDER BY day
            """)
            days_raw = cur.fetchall()
            days_labels = [str(r['day']) for r in days_raw]
            days_data   = [r['cnt'] for r in days_raw]

            cur.execute("""
                SELECT wu.vk_id, wu.first_name, wu.last_name, COUNT(ae.id) AS cnt,
                       MAX(ae.seen_time) AT TIME ZONE 'Europe/Moscow' AS last_seen
                FROM activity_events ae
                JOIN watched_users wu ON ae.vk_id = wu.vk_id
                GROUP BY wu.vk_id, wu.first_name, wu.last_name
                ORDER BY cnt DESC LIMIT 10
            """)
            top_users = cur.fetchall()

            cur.execute("""
                SELECT p.name, COUNT(ae.id) AS cnt
                FROM activity_events ae JOIN platforms p ON ae.platform_id = p.id
                WHERE p.name NOT IN ('none', 'unknown')
                GROUP BY p.name ORDER BY cnt DESC
            """)
            platforms = cur.fetchall()
            plat_labels = [r['name'] for r in platforms]
            plat_data   = [r['cnt'] for r in platforms]

            cur.execute("""
                SELECT EXTRACT(DOW FROM seen_time AT TIME ZONE 'Europe/Moscow')::int AS dow, COUNT(*) AS cnt
                FROM activity_events GROUP BY dow ORDER BY dow
            """)
            dow_raw = {r['dow']: r['cnt'] for r in cur.fetchall()}
            dow_labels = ['Вс','Пн','Вт','Ср','Чт','Пт','Сб']
            dow_data = [dow_raw.get(i, 0) for i in range(7)]

    return render_template('dashboard.html',
                           today_count=today_count, week_count=week_count,
                           month_count=month_count, total_count=total_count,
                           by_hour=by_hour, days_labels=days_labels, days_data=days_data,
                           top_users=top_users,
                           plat_labels=plat_labels, plat_data=plat_data,
                           dow_labels=dow_labels, dow_data=dow_data)


# User detail
# Детальная страница одного пользователя: графики активности и последние события

@app.route('/users/<int:vk_id>')
@login_required
def user_detail(vk_id):
    with get_db() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT * FROM watched_users WHERE vk_id = %s", (vk_id,))
            user = cur.fetchone()
            if not user:
                flash('Пользователь не найден', 'warning')
                return redirect(url_for('watched_users_list'))

            cur.execute("""
                SELECT EXTRACT(HOUR FROM seen_time AT TIME ZONE 'Europe/Moscow')::int AS hour, COUNT(*) AS cnt
                FROM activity_events WHERE vk_id = %s GROUP BY hour ORDER BY hour
            """, (vk_id,))
            hour_raw = {r['hour']: r['cnt'] for r in cur.fetchall()}
            by_hour = [hour_raw.get(h, 0) for h in range(24)]

            cur.execute("""
                SELECT DATE(seen_time AT TIME ZONE 'Europe/Moscow') AS day, COUNT(*) AS cnt
                FROM activity_events WHERE vk_id = %s AND seen_time >= NOW() - INTERVAL '30 days'
                GROUP BY day ORDER BY day
            """, (vk_id,))
            days_raw = cur.fetchall()
            days_labels = [str(r['day']) for r in days_raw]
            days_data   = [r['cnt'] for r in days_raw]

            cur.execute("""
                SELECT p.name, COUNT(*) AS cnt
                FROM activity_events ae JOIN platforms p ON ae.platform_id = p.id
                WHERE ae.vk_id = %s GROUP BY p.name ORDER BY cnt DESC
            """, (vk_id,))
            platforms = cur.fetchall()

            cur.execute("""
                SELECT ae.seen_time AT TIME ZONE 'Europe/Moscow' AS seen_time, p.name AS platform
                FROM activity_events ae JOIN platforms p ON ae.platform_id = p.id
                WHERE ae.vk_id = %s ORDER BY ae.seen_time DESC LIMIT 100
            """, (vk_id,))
            events = cur.fetchall()

            cur.execute("SELECT COUNT(*) AS cnt FROM activity_events WHERE vk_id = %s", (vk_id,))
            total = cur.fetchone()['cnt']

    return render_template('user_detail.html', user=user, by_hour=by_hour,
                           days_labels=days_labels, days_data=days_data,
                           platforms=platforms, events=events, total=total)


# CSV export
# Выгрузка событий активности с фильтрацией по датам и пользователю

@app.route('/export/csv')
@login_required
def export_csv():
    date_from = request.args.get('date_from', '')
    date_to   = request.args.get('date_to', '')
    vk_id     = request.args.get('vk_id', '')

    query = """
        SELECT ae.vk_id, wu.last_name, wu.first_name,
               ae.seen_time AT TIME ZONE 'Europe/Moscow' AS seen_time, p.name AS platform
        FROM activity_events ae
        LEFT JOIN watched_users wu ON ae.vk_id = wu.vk_id
        LEFT JOIN platforms p ON ae.platform_id = p.id WHERE 1=1
    """
    params = []
    if date_from:
        try:
            query += " AND ae.seen_time >= %s"
            params.append(tz_moscow.localize(datetime.strptime(date_from, "%d.%m.%Y")))
        except ValueError:
            pass
    if date_to:
        try:
            query += " AND ae.seen_time <= %s"
            params.append(tz_moscow.localize(datetime.strptime(date_to, "%d.%m.%Y").replace(hour=23, minute=59, second=59)))
        except ValueError:
            pass
    if vk_id.isdigit():
        query += " AND ae.vk_id = %s"
        params.append(int(vk_id))
    query += " ORDER BY ae.seen_time DESC"

    with get_db() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(query, params)
            rows = cur.fetchall()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['vk_id', 'Фамилия', 'Имя', 'Дата и время', 'Платформа'])
    for r in rows:
        writer.writerow([r['vk_id'], r['last_name'] or '', r['first_name'] or '',
                         r['seen_time'].strftime('%d.%m.%Y %H:%M:%S'), r['platform'] or ''])

    filename = f"activity_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    return Response(output.getvalue(), mimetype='text/csv; charset=utf-8',
                    headers={'Content-Disposition': f'attachment; filename={filename}'})


# Timeline
# Визуальная временная шкала: события нескольких пользователей на одном графике

@app.route('/timeline')
@login_required
def timeline():
    user_id = session.get('user_id')
    today   = datetime.now(tz_moscow).strftime("%d.%m.%Y")

    date_from     = request.args.get('date_from', today)
    date_to       = request.args.get('date_to',   today)
    vk_id_filters = request.args.getlist('vk_ids[]')

    try:
        from_dt = tz_moscow.localize(datetime.strptime(date_from, "%d.%m.%Y").replace(hour=0,  minute=0,  second=0))
        to_dt   = tz_moscow.localize(datetime.strptime(date_to,   "%d.%m.%Y").replace(hour=23, minute=59, second=59))
    except ValueError:
        from_dt = to_dt = datetime.now(tz_moscow)

    with get_db() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT vk_id, first_name, last_name FROM watched_users ORDER BY last_name, first_name")
            watched_users = cur.fetchall()

            query = """
                SELECT ae.vk_id,
                       EXTRACT(EPOCH FROM ae.seen_time AT TIME ZONE 'Europe/Moscow')::bigint AS ts,
                       ae.seen_time AT TIME ZONE 'Europe/Moscow' AS seen_time,
                       p.name AS platform
                FROM activity_events ae
                LEFT JOIN platforms p ON ae.platform_id = p.id
                WHERE ae.seen_time >= %s AND ae.seen_time <= %s
            """
            params = [from_dt, to_dt]
            if vk_id_filters:
                query += " AND ae.vk_id = ANY(%s)"
                params.append([int(v) for v in vk_id_filters])
            query += " ORDER BY ae.seen_time ASC"
            cur.execute(query, params)
            raw_events = cur.fetchall()

    color_map = _load_user_colors(user_id) if user_id else {}

    event_vk_ids = {e['vk_id'] for e in raw_events}
    if vk_id_filters:
        display_users = [u for u in watched_users if str(u['vk_id']) in vk_id_filters]
    else:
        display_users = [u for u in watched_users if u['vk_id'] in event_vk_ids]

    events_json   = json.dumps([{
        'vk_id':    e['vk_id'],
        'ts':       e['ts'] * 1000,  # milliseconds for Chart.js
        'platform': e['platform'] or '',
        'time_str': e['seen_time'].strftime('%d.%m.%Y %H:%M:%S'),
    } for e in raw_events])
    users_json    = json.dumps([{
        'vk_id':      u['vk_id'],
        'first_name': u['first_name'] or '',
        'last_name':  u['last_name']  or '',
    } for u in display_users])
    color_map_json = json.dumps({str(k): v for k, v in color_map.items()})

    return render_template('timeline.html',
                           watched_users=watched_users,
                           date_from=date_from, date_to=date_to,
                           vk_id_filters=vk_id_filters,
                           events_json=events_json,
                           users_json=users_json,
                           color_map_json=color_map_json)


# Цвет пользователя

@app.route('/users/color/<int:vk_id>', methods=['POST'])
@login_required
def set_user_color(vk_id):
    color   = request.form.get('color', '').strip()
    user_id = session.get('user_id')
    if not user_id:
        return redirect(url_for('watched_users_list'))

    with get_db() as conn:
        with conn.cursor() as cur:
            if color and color.startswith('#'):
                cur.execute("""
                    INSERT INTO user_vk_colors (app_user_id, vk_id, color)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (app_user_id, vk_id) DO UPDATE SET color = EXCLUDED.color
                """, (user_id, vk_id, color))
            else:
                cur.execute("DELETE FROM user_vk_colors WHERE app_user_id = %s AND vk_id = %s",
                            (user_id, vk_id))
        conn.commit()
    return redirect(url_for('watched_users_list'))


# Админ-панель

@app.route('/admin/users')
@admin_required
def admin_users():
    with get_db() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT id, username, name, is_admin, created_at FROM app_users ORDER BY created_at")
            users = cur.fetchall()
    return render_template('admin_users.html', users=users)


@app.route('/admin/users/add', methods=['POST'])
@admin_required
def admin_add_user():
    username = request.form.get('username', '').strip()
    name     = request.form.get('name', '').strip()
    password = request.form.get('password', '')
    is_admin = bool(request.form.get('is_admin'))

    if not username or not password or not name:
        flash('Все поля обязательны', 'danger')
        return redirect(url_for('admin_users'))

    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO app_users (username, password_hash, name, is_admin) VALUES (%s, %s, %s, %s)",
                    (username, generate_password_hash(password), name, is_admin)
                )
            conn.commit()
        flash(f'Пользователь {username} добавлен', 'success')
    except psycopg2.errors.UniqueViolation:
        flash(f'Логин «{username}» уже занят', 'danger')
    except Exception as e:
        flash(f'Ошибка: {e}', 'danger')

    return redirect(url_for('admin_users'))


@app.route('/admin/users/password/<int:user_id>', methods=['POST'])
@admin_required
def admin_change_password(user_id):
    password = request.form.get('password', '')
    if len(password) < 4:
        flash('Пароль слишком короткий (минимум 4 символа)', 'danger')
        return redirect(url_for('admin_users'))

    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE app_users SET password_hash = %s WHERE id = %s",
                        (generate_password_hash(password), user_id))
        conn.commit()
    flash('Пароль обновлён', 'success')
    return redirect(url_for('admin_users'))


@app.route('/admin/users/toggle/<int:user_id>', methods=['POST'])
@admin_required
def admin_toggle_admin(user_id):
    # Нельзя снять права с себя
    with get_db() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT username, is_admin FROM app_users WHERE id = %s", (user_id,))
            u = cur.fetchone()
        if u and u['username'] == session['username']:
            flash('Нельзя изменить права своего аккаунта', 'warning')
            return redirect(url_for('admin_users'))
        with conn.cursor() as cur:
            cur.execute("UPDATE app_users SET is_admin = NOT is_admin WHERE id = %s", (user_id,))
        conn.commit()
    flash('Права обновлены', 'success')
    return redirect(url_for('admin_users'))


@app.route('/admin/users/delete/<int:user_id>', methods=['POST'])
@admin_required
def admin_delete_user(user_id):
    with get_db() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT username FROM app_users WHERE id = %s", (user_id,))
            u = cur.fetchone()
        if u and u['username'] == session['username']:
            flash('Нельзя удалить собственный аккаунт', 'warning')
            return redirect(url_for('admin_users'))
        with conn.cursor() as cur:
            cur.execute("DELETE FROM app_users WHERE id = %s", (user_id,))
        conn.commit()
    flash('Пользователь удалён', 'success')
    return redirect(url_for('admin_users'))
