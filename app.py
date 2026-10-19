import os
import sqlite3
from functools import wraps
from pathlib import Path
import secrets
from urllib.parse import quote

from flask import Flask, abort, flash, redirect, render_template_string, request, session, url_for

BASE_DIR = Path(__file__).resolve().parent


def load_env_file(path):
    """Load simple KEY=VALUE entries without overriding the shell environment."""
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key, value = key.strip(), value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        if key:
            os.environ.setdefault(key, value)


load_env_file(BASE_DIR / ".env")
if not os.environ.get("SECRET_KEY"):
    os.environ["SECRET_KEY"] = secrets.token_urlsafe(48)
DB_PATH = Path(os.environ.get("REPAIR_DB", BASE_DIR / "repairs.sqlite3"))
app = Flask(__name__)
app.secret_key = os.environ["SECRET_KEY"]
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax")


def db():
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def init_db():
    with db() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            position INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS services (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category_id INTEGER NOT NULL REFERENCES categories(id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            price REAL,
            unit TEXT NOT NULL DEFAULT 'кв.м',
            position INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        """)
        if conn.execute("SELECT COUNT(*) FROM categories").fetchone()[0] == 0:
            examples = [
                ("Боядисване и шпакловка", [("Боядисване с латекс", "Подготовка и боядисване на стени и тавани.", 8.0, "кв.м"), ("Фина шпакловка", "Изравняване и подготовка за боядисване.", 12.0, "кв.м")]),
                ("Подови настилки", [("Редене на ламинат", "Монтаж на ламинат с подложка.", 18.0, "кв.м"), ("Полагане на гранитогрес", "Прецизно лепене и фугиране.", 45.0, "кв.м")]),
                ("Баня и ВиК", [("Основен ремонт на баня", "Цена след оглед според обхвата.", None, "проект"), ("Монтаж на санитария", "Монтаж и свързване на санитарно оборудване.", 80.0, "бр.")]),
                ("Електроуслуги", [("Монтаж на контакт", "Демонтаж и монтаж на контакт.", 25.0, "бр.")]),
            ]
            for cat_pos, (category, items) in enumerate(examples):
                cur = conn.execute("INSERT INTO categories(name, position) VALUES (?, ?)", (category, cat_pos))
                for pos, (name, description, price, unit) in enumerate(items):
                    conn.execute("INSERT INTO services(category_id,name,description,price,unit,position) VALUES (?,?,?,?,?,?)", (cur.lastrowid, name, description, price, unit, pos))
        for key, value in (("company_name", "Вътрешни ремонти"), ("legal_name", "Вионекс ДГ ЕООД"), ("eik", "208377941"), ("address", "гр. София, район Студентски, ж.к. Витоша, бл. 1, ет. 2, ап. 6"), ("phone", "359888123456"), ("city", "София и областта")):
            conn.execute("INSERT OR IGNORE INTO settings(key,value) VALUES (?,?)", (key, value))


init_db()

STYLE = """
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=Manrope:wght@400;500;600;700;800&display=swap');
:root{--ink:#172321;--muted:#6c7773;--green:#234c3b;--lime:#d2ed83;--paper:#f7f7f2;--line:#e3e7df}*{box-sizing:border-box}body{margin:0;background:var(--paper);color:var(--ink);font:16px 'DM Sans',sans-serif}a{color:inherit;text-decoration:none}.wrap{width:min(1120px,calc(100% - 40px));margin:auto}.top{height:76px;display:flex;align-items:center;justify-content:space-between}.brand{font:800 20px Manrope,sans-serif;letter-spacing:-.7px}.brand span{color:#82994d}.nav{display:flex;gap:26px;color:#50605a;font-size:14px}.contact{background:var(--green);color:white;padding:12px 18px;border-radius:7px;font-size:14px;font-weight:700}.hero{background:var(--green);color:#fff;border-radius:18px;min-height:380px;padding:68px 7%;position:relative;overflow:hidden;display:flex;align-items:center}.hero:after{content:'⌂';position:absolute;right:5%;bottom:-180px;font:400 440px Manrope;color:#ffffff0a}.eyebrow{color:var(--lime);font-size:12px;font-weight:700;letter-spacing:1.8px;text-transform:uppercase}.hero h1{font:800 clamp(40px,6vw,68px)/1.04 Manrope;margin:16px 0;letter-spacing:-3px;max-width:650px}.hero p{color:#d6e0d9;max-width:490px;line-height:1.7}.actions{display:flex;gap:12px;margin-top:28px}.btn{display:inline-block;padding:14px 20px;border-radius:7px;font-weight:700;font-size:14px}.btn-lime{background:var(--lime);color:#1d3329}.btn-outline{border:1px solid #ffffff66;color:white}.section{padding:64px 0}.section-head{display:flex;align-items:end;justify-content:space-between;margin-bottom:26px}.section h2{font:800 32px Manrope;letter-spacing:-1.2px;margin:8px 0}.section-head p{color:var(--muted);margin:0}.category{margin:30px 0}.category h3{font:700 19px Manrope;margin:0 0 12px}.cards{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}.card{background:white;border:1px solid var(--line);padding:20px;border-radius:10px}.card h4{font:700 16px Manrope;margin:0 0 8px}.card p{font-size:13px;color:var(--muted);line-height:1.55;min-height:40px;margin:0}.price{font-weight:700;margin-top:18px}.price small{font-weight:400;color:var(--muted)}.band{background:#eaf0e4;border-radius:14px;padding:30px;display:flex;justify-content:space-between;align-items:center}.band h2{font:800 24px Manrope;margin:0 0 6px}.band p{color:var(--muted);margin:0}.footer{padding:25px 0;color:var(--muted);font-size:13px;border-top:1px solid var(--line)}.wa{position:fixed;right:22px;bottom:22px;background:#20b96b;color:white;padding:13px 18px;border-radius:40px;font-weight:700;box-shadow:0 7px 24px #103b2533}.admin{max-width:900px;margin:35px auto}.admin h1{font:800 32px Manrope}.panel{background:white;border:1px solid var(--line);border-radius:10px;padding:22px;margin:18px 0}.row{display:flex;gap:10px;align-items:center;flex-wrap:wrap}.row>*{flex:1}.form-grid{display:grid;grid-template-columns:repeat(2,1fr);gap:12px}input,textarea,select{width:100%;padding:11px 12px;border:1px solid #d5dcd4;border-radius:6px;font:inherit;background:white}textarea{min-height:78px}label{display:block;font-size:12px;color:var(--muted);margin-bottom:5px}.submit{border:0;background:var(--green);color:white;border-radius:6px;padding:11px 16px;font:700 14px 'DM Sans';cursor:pointer}.danger{color:#a13e35;background:none;border:0;cursor:pointer}.item{border-top:1px solid var(--line);padding-top:14px;margin-top:14px}.flash{padding:12px;background:#eff6dc;border-radius:6px;margin:10px 0}.hint{font-size:12px;color:var(--muted)}@media(max-width:700px){.nav{display:none}.hero{padding:42px 26px;min-height:360px}.cards{grid-template-columns:1fr}.section-head,.band{display:block}.band .contact{display:inline-block;margin-top:18px}.form-grid{grid-template-columns:1fr}.top{height:66px}.wa{right:12px;bottom:12px}}
"""

PUBLIC = """<!doctype html><html lang="bg"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>{{ settings.company_name }} | Вътрешни ремонти</title><style>{{ style }}.contact-grid{display:grid;grid-template-columns:.8fr 1.2fr;gap:18px}.contact-info{background:white;border:1px solid var(--line);padding:25px;border-radius:12px}.contact-info p{line-height:1.6;color:var(--muted)}.map{width:100%;height:290px;border:0;border-radius:12px}.map-actions{display:flex;gap:10px;flex-wrap:wrap;margin-top:15px}@media(max-width:700px){.contact-grid{grid-template-columns:1fr}}</style></head><body><div class="wrap"><header class="top"><a class="brand" href="/">{{ settings.company_name }}<span>.</span></a><nav class="nav"><a href="#uslugi">Услуги и цени</a><a href="#kontakt">Контакти</a></nav><a class="contact" href="{{ wa }}" target="_blank" rel="noopener">Пиши ни в WhatsApp ↗</a></header><main><section class="hero"><div><div class="eyebrow">Вътрешни ремонти · {{ settings.city }}</div><h1>Домът ти.<br>Направен както трябва.</h1><p>Качествени ремонти и довършителни дейности с ясни цени, коректно отношение и внимание към детайла.</p><div class="actions"><a class="btn btn-lime" href="#uslugi">Разгледай услугите ↓</a><a class="btn btn-outline" href="{{ wa }}" target="_blank" rel="noopener">Запитване в WhatsApp</a></div></div></section><section class="section" id="uslugi"><div class="section-head"><div><div class="eyebrow" style="color:#708346">Ценоразпис</div><h2>Услуги и ориентировъчни цени</h2><p>Цените са за труд. Точна оферта след оглед.</p></div></div>{% for category in categories %}<div class="category"><h3>{{ category.name }}</h3><div class="cards">{% for service in category.services %}<article class="card"><h4>{{ service.name }}</h4><p>{{ service.description }}</p><div class="price">{% if service.price is not none %}от {{ '%.2f'|format(service.price)|replace('.', ',') }} € <small>/ {{ service.unit }}</small>{% else %}По договаряне{% endif %}</div></article>{% endfor %}</div></div>{% endfor %}</section><section class="section" id="kontakt"><div class="section-head"><div><div class="eyebrow" style="color:#708346">Контакти</div><h2>Свържи се с нас</h2><p>Пиши ни за оферта или посети адреса на фирмата.</p></div></div><div class="contact-grid"><div class="contact-info"><h3>{{ settings.legal_name }}</h3><p>ЕИК: {{ settings.eik }}</p><p><b>Адрес:</b><br>{{ settings.address }}</p><p><b>Район на работа:</b><br>{{ settings.city }}</p><div class="map-actions"><a class="contact" href="{{ directions }}" target="_blank" rel="noopener">Упътвания в Google Maps ↗</a><a class="btn" style="background:#20b96b;color:white" href="{{ wa }}" target="_blank" rel="noopener">WhatsApp ↗</a></div></div><div><iframe class="map" title="Карта с адреса на фирмата" src="{{ map_embed }}" loading="lazy" referrerpolicy="no-referrer-when-downgrade" allowfullscreen></iframe></div></div></section></main><footer class="footer">© {{ settings.company_name }} · {{ settings.city }} · Цените са ориентировъчни.</footer></div><a class="wa" href="{{ wa }}" target="_blank" rel="noopener">WhatsApp ↗</a></body></html>"""

LOGIN = """<!doctype html><html lang="bg"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>Вход · Админ</title><style>{{ style }}.box{max-width:400px;margin:10vh auto;background:white;padding:30px;border-radius:12px;border:1px solid var(--line)}.box h1{font:800 28px Manrope}.box input{margin-bottom:12px}</style><div class="box"><a class="brand" href="/">{{ company }}<span>.</span></a><h1>Администрация</h1>{% for message in get_flashed_messages() %}<div class="flash">{{ message }}</div>{% endfor %}<form method="post"><label>Парола</label><input type="password" name="password" required autofocus><button class="submit">Вход</button></form><p class="hint">Паролата се задава чрез променливата ADMIN_PASSWORD.</p></div></html>"""

ADMIN = """<!doctype html><html lang="bg"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>Админ · {{ settings.company_name }}</title><style>{{ style }}</style></head><body><main class="wrap admin"><div class="row"><div><div class="eyebrow" style="color:#708346">Администрация</div><h1>Управление на ценоразписа</h1></div><a href="/" class="contact">Към сайта ↗</a><a href="/admin/logout">Изход</a></div>{% for message in get_flashed_messages() %}<div class="flash">{{ message }}</div>{% endfor %}<section class="panel"><h2>Данни за фирмата</h2><form method="post" action="/admin/settings"><div class="form-grid"><div><label>Име на фирмата</label><input name="company_name" value="{{ settings.company_name }}" required></div><div><label>Град / район на работа</label><input name="city" value="{{ settings.city }}"></div><div><label>Юридическо име на фирмата</label><input name="legal_name" value="{{ settings.legal_name }}"></div><div><label>ЕИК</label><input name="eik" value="{{ settings.eik }}"></div><div><label>Адрес за картата и упътванията</label><input name="address" value="{{ settings.address }}"></div><div><label>Телефон за WhatsApp (международен формат, само цифри)</label><input name="phone" value="{{ settings.phone }}" placeholder="359888123456" required><small class="hint">Стойността от WHATSAPP_PHONE в .env има предимство.</small></div></div><p><button class="submit">Запази данните</button></p></form></section><section class="panel"><h2>Добави категория</h2><form method="post" action="/admin/category" class="row"><input name="name" placeholder="Напр. Бояджийски услуги" required><button class="submit">Добави</button></form></section>{% for category in categories %}<section class="panel"><div class="row"><h2>{{ category.name }}</h2><form method="post" action="/admin/category/{{ category.id }}/rename" class="row"><input name="name" value="{{ category.name }}" required><button class="submit">Преименувай</button></form><form method="post" action="/admin/category/{{ category.id }}/delete" onsubmit="return confirm('Да изтрия ли категорията и услугите в нея?')"><button class="danger">Изтрий категория</button></form></div><form method="post" action="/admin/service" class="panel"><h3>Нова услуга</h3><input type="hidden" name="category_id" value="{{ category.id }}"><div class="form-grid"><div><label>Наименование</label><input name="name" required></div><div><label>Цена в евро (остави празно за „по договаряне“)</label><input name="price" type="number" step="0.01" min="0"></div><div><label>Мерна единица</label><input name="unit" value="кв.м"></div><div><label>Описание</label><input name="description"></div></div><p><button class="submit">Добави услуга</button></p></form>{% for service in category.services %}<form method="post" action="/admin/service/{{ service.id }}/edit" class="item"><div class="form-grid"><div><label>Наименование</label><input name="name" value="{{ service.name }}" required></div><div><label>Цена в евро (празно = по договаряне)</label><input name="price" type="number" step="0.01" min="0" value="{{ service.price if service.price is not none else '' }}"></div><div><label>Мерна единица</label><input name="unit" value="{{ service.unit }}"></div><div><label>Описание</label><input name="description" value="{{ service.description }}"></div></div><p><button class="submit">Запази промените</button> <button class="danger" formaction="/admin/service/{{ service.id }}/delete" formmethod="post" onclick="return confirm('Да изтрия ли услугата?')">Изтрий</button></p></form>{% endfor %}</section>{% endfor %}</main></body></html>"""


def settings_dict(conn):
    return {row["key"]: row["value"] for row in conn.execute("SELECT key,value FROM settings")}


def whatsapp(settings):
    configured_phone = os.environ.get("WHATSAPP_PHONE") or settings.get("phone", "")
    number = "".join(ch for ch in configured_phone if ch.isdigit())
    return f"https://wa.me/{number}?text=%D0%97%D0%B4%D1%80%D0%B0%D0%B2%D0%B5%D0%B9%D1%82%D0%B5%2C%20%D0%B8%D0%BD%D1%82%D0%B5%D1%80%D0%B5%D1%81%D1%83%D0%B2%D0%B0%D0%BC%20%D1%81%D0%B5%20%D0%BE%D1%82%20%D0%B2%D0%B0%D1%88%D0%B8%D1%82%D0%B5%20%D1%83%D1%81%D0%BB%D1%83%D0%B3%D0%B8." if number else "https://wa.me/"


def map_links(settings):
    query = settings.get("address", "")
    return f"https://www.google.com/maps?q={quote(query)}&output=embed", f"https://www.google.com/maps/dir/?api=1&destination={quote(query)}"


@app.get("/")
def index():
    with db() as conn:
        settings = settings_dict(conn)
        categories = conn.execute("SELECT * FROM categories ORDER BY position,id").fetchall()
        data = [{**dict(c), "services": [dict(s) for s in conn.execute("SELECT * FROM services WHERE category_id=? ORDER BY position,id", (c["id"],))]} for c in categories]
    map_embed, directions = map_links(settings)
    return render_template_string(PUBLIC, categories=data, settings=settings, wa=whatsapp(settings), map_embed=map_embed, directions=directions, style=STYLE)


def admin_required(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        if not session.get("admin"):
            return redirect(url_for("admin_login"))
        return fn(*args, **kwargs)
    return wrapped


@app.route("/admin", methods=["GET", "POST"])
def admin_login():
    if session.get("admin"):
        return redirect(url_for("admin_dashboard"))
    with db() as conn:
        company = settings_dict(conn).get("company_name", "Админ")
    if request.method == "POST":
        expected = os.environ.get("ADMIN_PASSWORD", "admin123")
        if request.form.get("password", "") == expected:
            session["admin"] = True
            return redirect(url_for("admin_dashboard"))
        flash("Невалидна парола.")
    return render_template_string(LOGIN, style=STYLE, company=company)


@app.get("/admin/logout")
def admin_logout():
    session.clear()
    return redirect(url_for("admin_login"))


@app.get("/admin/dashboard")
@admin_required
def admin_dashboard():
    with db() as conn:
        settings = settings_dict(conn)
        categories = conn.execute("SELECT * FROM categories ORDER BY position,id").fetchall()
        data = [{**dict(c), "services": [dict(s) for s in conn.execute("SELECT * FROM services WHERE category_id=? ORDER BY position,id", (c["id"],))]} for c in categories]
    return render_template_string(ADMIN, style=STYLE, settings=settings, categories=data)


@app.post("/admin/settings")
@admin_required
def save_settings():
    allowed = {"company_name", "legal_name", "eik", "address", "phone", "city"}
    values = {k: request.form.get(k, "").strip() for k in allowed}
    if not values["company_name"] or not values["phone"]:
        flash("Име и телефон са задължителни.")
        return redirect(url_for("admin_dashboard"))
    with db() as conn:
        conn.executemany("INSERT INTO settings(key,value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", values.items())
    flash("Данните са запазени.")
    return redirect(url_for("admin_dashboard"))


@app.post("/admin/category")
@admin_required
def add_category():
    name = request.form.get("name", "").strip()
    if name:
        try:
            with db() as conn:
                conn.execute("INSERT INTO categories(name,position) VALUES (?, (SELECT COALESCE(MAX(position),0)+1 FROM categories))", (name,))
            flash("Категорията е добавена.")
        except sqlite3.IntegrityError:
            flash("Тази категория вече съществува.")
    return redirect(url_for("admin_dashboard"))


@app.post("/admin/category/<int:category_id>/rename")
@admin_required
def rename_category(category_id):
    try:
        with db() as conn:
            conn.execute("UPDATE categories SET name=? WHERE id=?", (request.form.get("name", "").strip(), category_id))
        flash("Категорията е обновена.")
    except sqlite3.IntegrityError:
        flash("Категория с това име вече съществува.")
    return redirect(url_for("admin_dashboard"))


@app.post("/admin/category/<int:category_id>/delete")
@admin_required
def delete_category(category_id):
    with db() as conn:
        conn.execute("DELETE FROM categories WHERE id=?", (category_id,))
    flash("Категорията и услугите в нея са изтрити.")
    return redirect(url_for("admin_dashboard"))


def parse_price(value):
    value = value.strip().replace(",", ".")
    return float(value) if value else None


@app.post("/admin/service")
@admin_required
def add_service():
    try:
        price = parse_price(request.form.get("price", ""))
        with db() as conn:
            conn.execute("INSERT INTO services(category_id,name,description,price,unit) VALUES (?,?,?,?,?)", (int(request.form["category_id"]), request.form["name"].strip(), request.form.get("description", "").strip(), price, request.form.get("unit", "кв.м").strip() or "бр."))
        flash("Услугата е добавена.")
    except (ValueError, KeyError, sqlite3.IntegrityError):
        flash("Провери въведените данни за услугата.")
    return redirect(url_for("admin_dashboard"))


@app.post("/admin/service/<int:service_id>/edit")
@admin_required
def edit_service(service_id):
    try:
        with db() as conn:
            conn.execute("UPDATE services SET name=?,description=?,price=?,unit=? WHERE id=?", (request.form["name"].strip(), request.form.get("description", "").strip(), parse_price(request.form.get("price", "")), request.form.get("unit", "").strip() or "бр.", service_id))
        flash("Услугата е обновена.")
    except (ValueError, KeyError):
        flash("Провери въведената цена.")
    return redirect(url_for("admin_dashboard"))


@app.post("/admin/service/<int:service_id>/delete")
@admin_required
def delete_service(service_id):
    with db() as conn:
        conn.execute("DELETE FROM services WHERE id=?", (service_id,))
    flash("Услугата е изтрита.")
    return redirect(url_for("admin_dashboard"))


if __name__ == "__main__":
    app.run(host=os.environ.get("HOST", "127.0.0.1"), port=int(os.environ.get("PORT", "5000")), debug=False)
