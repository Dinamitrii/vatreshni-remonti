import os
import sqlite3
from functools import wraps
from pathlib import Path
import secrets
from urllib.parse import quote
from xml.sax.saxutils import escape

from flask import Flask, Response, abort, flash, redirect, render_template, request, session, url_for

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






def public_site_url():
    configured_url = os.environ.get("SITE_URL", "").strip().rstrip("/")
    return configured_url or request.url_root.rstrip("/")


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
    return render_template("index.html", categories=data, settings=settings, wa=whatsapp(settings), map_embed=map_embed, directions=directions, canonical_url=f"{public_site_url()}/")


@app.get("/sitemap.xml")
def sitemap():
    homepage = escape(f"{public_site_url()}/")
    xml = f'''<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>{homepage}</loc></url>
</urlset>'''
    return Response(xml, mimetype="application/xml")


@app.get("/robots.txt")
def robots():
    sitemap_url = escape(f"{public_site_url()}/sitemap.xml")
    body = f"User-agent: *\nAllow: /\nDisallow: /admin\nSitemap: {sitemap_url}\n"
    return Response(body, mimetype="text/plain")


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
    return render_template("login.html", company=company)


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
    return render_template("admin.html", settings=settings, categories=data)


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
