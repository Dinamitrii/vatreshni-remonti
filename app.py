import os
import sqlite3
from functools import wraps
from pathlib import Path
import secrets
from uuid import uuid4
from urllib.parse import quote
from xml.sax.saxutils import escape

from PIL import Image, ImageOps, UnidentifiedImageError
from responsive_images import generate as generate_responsive_image, install as install_responsive_images, remove_responsive_variants

from flask import Flask, Response, abort, flash, redirect, render_template, request, send_from_directory, session, url_for

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
CATEGORY_IMAGE_DIR = BASE_DIR / "static" / "uploads" / "categories"
ALLOWED_IMAGE_FORMATS = {"JPEG", "PNG", "WEBP"}
MAX_UPLOAD_BYTES = 12 * 1024 * 1024
MAX_IMAGE_EDGE = 2400
app = Flask(__name__)
app.secret_key = os.environ["SECRET_KEY"]
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax", MAX_CONTENT_LENGTH=MAX_UPLOAD_BYTES + 1024 * 1024)
install_responsive_images(app)


def db():
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def remove_uploaded_image(filename):
    path = BASE_DIR / "static" / filename
    remove_responsive_variants(path)
    path.unlink(missing_ok=True)


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
        CREATE TABLE IF NOT EXISTS category_images (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category_id INTEGER NOT NULL REFERENCES categories(id) ON DELETE CASCADE,
            service_id INTEGER REFERENCES services(id) ON DELETE CASCADE,
            filename TEXT NOT NULL UNIQUE,
            alt TEXT NOT NULL DEFAULT '',
            position INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        """)
        image_columns = {row["name"] for row in conn.execute("PRAGMA table_info(category_images)")}
        if "service_id" not in image_columns:
            conn.execute("ALTER TABLE category_images ADD COLUMN service_id INTEGER REFERENCES services(id) ON DELETE CASCADE")
        legacy_images = conn.execute("""
            SELECT id, category_id, alt FROM category_images
            WHERE service_id IS NULL
              AND EXISTS (SELECT 1 FROM services WHERE services.category_id=category_images.category_id)
            ORDER BY category_id, position, id
        """).fetchall()
        for image in legacy_images:
            services = conn.execute(
                "SELECT id,name FROM services WHERE category_id=? ORDER BY position,id",
                (image["category_id"],),
            ).fetchall()
            image_alt = image["alt"].casefold()
            target = next((service for service in services if service["name"].casefold() in image_alt), services[0])
            position = conn.execute(
                "SELECT COALESCE(MAX(position),-1)+1 FROM category_images WHERE service_id=?",
                (target["id"],),
            ).fetchone()[0]
            conn.execute("UPDATE category_images SET service_id=?,position=? WHERE id=?", (target["id"], position, image["id"]))
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


@app.get("/favicon_io/<path:filename>")
def favicon_asset(filename):
    allowed_files = {
        "favicon.ico", "favicon-16x16.png", "favicon-32x32.png",
        "apple-touch-icon.png", "android-chrome-192x192.png",
        "android-chrome-512x512.png", "site.webmanifest",
    }
    if filename not in allowed_files:
        abort(404)
    return send_from_directory(BASE_DIR / "favicon_io", filename)


@app.get("/favicon.ico")
def root_favicon():
    return send_from_directory(BASE_DIR / "favicon_io", "favicon.ico")


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
        data = []
        for category in categories:
            services = []
            for service in conn.execute("SELECT * FROM services WHERE category_id=? ORDER BY position,id", (category["id"],)):
                service_data = dict(service)
                service_data["images"] = [dict(image) for image in conn.execute(
                    "SELECT * FROM category_images WHERE service_id=? ORDER BY position,id", (service["id"],)
                )]
                services.append(service_data)
            data.append({**dict(category), "services": services})
    map_embed, directions = map_links(settings)
    return render_template("index.html", categories=data, settings=settings, wa=whatsapp(settings), map_embed=map_embed, directions=directions, canonical_url=f"{public_site_url()}/")


@app.get("/kontakti")
def contact_page():
    with db() as conn:
        settings = settings_dict(conn)
    map_embed, directions = map_links(settings)
    return render_template(
        "contact.html",
        settings=settings,
        wa=whatsapp(settings),
        map_embed=map_embed,
        directions=directions,
        canonical_url=f"{public_site_url()}{url_for('contact_page')}",
    )


@app.get("/sitemap.xml")
def sitemap():
    base_url = public_site_url()
    homepage = escape(f"{base_url}/")
    contacts_page_url = escape(f"{base_url}{url_for('contact_page')}")
    with db() as conn:
        images = conn.execute("""
            SELECT ci.filename, ci.alt, c.name AS category_name, s.name AS service_name
            FROM category_images ci JOIN categories c ON c.id=ci.category_id
            LEFT JOIN services s ON s.id=ci.service_id
            ORDER BY c.position,c.id,s.position,s.id,ci.position,ci.id
        """).fetchall()
    image_entries = "\n".join(
        "    <image:image><image:loc>" + escape(f"{base_url}{url_for('static', filename=image['filename'])}") + "</image:loc>" +
        ("<image:title>" + escape(image["alt"] or image["service_name"] or image["category_name"]) + "</image:title>" if image["alt"] or image["service_name"] or image["category_name"] else "") +
        "</image:image>"
        for image in images
    )
    xml = f'''<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" xmlns:image="http://www.google.com/schemas/sitemap-image/1.1">
<url><loc>{homepage}</loc>{image_entries}</url>
  <url><loc>{contacts_page_url}</loc></url>
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
        data = []
        for category in categories:
            services = []
            for service in conn.execute("SELECT * FROM services WHERE category_id=? ORDER BY position,id", (category["id"],)):
                service_data = dict(service)
                service_data["images"] = [dict(image) for image in conn.execute(
                    "SELECT * FROM category_images WHERE service_id=? ORDER BY position,id", (service["id"],)
                )]
                services.append(service_data)
            data.append({**dict(category), "services": services})
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


@app.post("/admin/category/<int:category_id>/position")
@admin_required
def set_category_position(category_id):
    try:
        position = max(0, int(request.form.get("position", "0")))
        with db() as conn:
            conn.execute("UPDATE categories SET position=? WHERE id=?", (position, category_id))
        flash("Подредбата на категорията е запазена.")
    except ValueError:
        flash("Въведи валиден номер за подредба.")
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
        filenames = [row[0] for row in conn.execute("SELECT filename FROM category_images WHERE category_id=?", (category_id,))]
    with db() as conn:
        conn.execute("DELETE FROM categories WHERE id=?", (category_id,))
    for filename in filenames:
        remove_uploaded_image(filename)
    flash("Категорията и услугите в нея са изтрити.")
    return redirect(url_for("admin_dashboard"))


def parse_price(value):
    value = value.strip().replace(",", ".")
    return float(value) if value else None


def save_optimized_image(file_storage):
    if not file_storage or not file_storage.filename:
        raise ValueError("Избери изображение за качване.")
    raw = file_storage.stream.read(MAX_UPLOAD_BYTES + 1)
    if len(raw) > MAX_UPLOAD_BYTES:
        raise ValueError("Изображението трябва да е до 12 MB.")
    try:
        from io import BytesIO
        with Image.open(BytesIO(raw)) as source:
            if source.format not in ALLOWED_IMAGE_FORMATS:
                raise ValueError("Поддържат се JPEG, PNG и WebP изображения.")
            source.verify()
        with Image.open(BytesIO(raw)) as source:
            image = ImageOps.exif_transpose(source)
            if image.width * image.height > 40_000_000:
                raise ValueError("Изображението е прекалено голямо.")
            image.thumbnail((MAX_IMAGE_EDGE, MAX_IMAGE_EDGE), Image.Resampling.LANCZOS)
            if image.mode not in ("RGB", "RGBA"):
                image = image.convert("RGBA" if "A" in image.getbands() else "RGB")
            CATEGORY_IMAGE_DIR.mkdir(parents=True, exist_ok=True)
            filename = f"{uuid4().hex}.webp"
            target = CATEGORY_IMAGE_DIR / filename
            image.save(target, "WEBP", quality=82, method=6)
            return f"uploads/categories/{filename}"
    except (UnidentifiedImageError, OSError, SyntaxError, Image.DecompressionBombError) as exc:
        raise ValueError("Файлът не е валидно изображение.") from exc


def save_image_to_service(service_id):
    saved_path = None
    try:
        with db() as conn:
            service = conn.execute("SELECT id,category_id FROM services WHERE id=?", (service_id,)).fetchone()
            if not service:
                abort(404)
        saved_path = save_optimized_image(request.files.get("image"))
        generate_responsive_image(BASE_DIR / "static" / saved_path)
        alt = request.form.get("alt", "").strip()[:250]
        with db() as conn:
            position = conn.execute("SELECT COALESCE(MAX(position),-1)+1 FROM category_images WHERE service_id=?", (service_id,)).fetchone()[0]
            conn.execute("INSERT INTO category_images(category_id,service_id,filename,alt,position) VALUES (?,?,?,?,?)", (service["category_id"], service_id, saved_path, alt, position))
        flash("Снимката е качена и оптимизирана до WebP.")
    except ValueError as exc:
        if saved_path:
            remove_uploaded_image(saved_path)
        flash(str(exc))
    except sqlite3.Error:
        if saved_path:
            remove_uploaded_image(saved_path)
        flash("Снимката не можа да бъде запазена.")
    return redirect(url_for("admin_dashboard"))


@app.post("/admin/service/<int:service_id>/images")
@admin_required
def upload_service_image(service_id):
    return save_image_to_service(service_id)


@app.post("/admin/category/<int:category_id>/images")
@admin_required
def upload_category_image(category_id):
    with db() as conn:
        service = conn.execute("SELECT id FROM services WHERE category_id=? ORDER BY position,id LIMIT 1", (category_id,)).fetchone()
    if not service:
        flash("Добави услуга към категорията, преди да качиш снимка.")
        return redirect(url_for("admin_dashboard"))
    return save_image_to_service(service["id"])


@app.post("/admin/category-image/<int:image_id>/edit")
@admin_required
def edit_category_image(image_id):
    try:
        position = max(0, int(request.form.get("position", "0")))
    except ValueError:
        flash("Въведи валиден номер за подредба.")
        return redirect(url_for("admin_dashboard"))
    replacement = None
    old_filename = None
    with db() as conn:
        current = conn.execute("SELECT filename FROM category_images WHERE id=?", (image_id,)).fetchone()
    if not current:
        abort(404)
    old_filename = current["filename"]
    try:
        replacement_file = request.files.get("image")
        if replacement_file and replacement_file.filename:
            replacement = save_optimized_image(replacement_file)
            generate_responsive_image(BASE_DIR / "static" / replacement)
        with db() as conn:
            filename = replacement or old_filename
            conn.execute("UPDATE category_images SET alt=?, position=?, filename=? WHERE id=?", (request.form.get("alt", "").strip()[:250], position, filename, image_id))
    except (ValueError, sqlite3.Error) as exc:
        if replacement:
            remove_uploaded_image(replacement)
        flash(str(exc) if isinstance(exc, ValueError) else "Промяната не можа да бъде запазена.")
        return redirect(url_for("admin_dashboard"))
    if replacement and old_filename:
        remove_uploaded_image(old_filename)
    flash("Описанието и подредбата на снимката са запазени.")
    return redirect(url_for("admin_dashboard"))


@app.get("/admin/category-image/<int:image_id>/export")
@admin_required
def export_category_image(image_id):
    with db() as conn:
        image = conn.execute("SELECT filename FROM category_images WHERE id=?", (image_id,)).fetchone()
    if not image:
        abort(404)
    path = BASE_DIR / "static" / image["filename"]
    if not path.is_file():
        abort(404)
    return app.response_class(path.read_bytes(), mimetype="image/webp", headers={"Content-Disposition": f'attachment; filename="category-image-{image_id}.webp"'})


@app.post("/admin/category-image/<int:image_id>/delete")
@admin_required
def delete_category_image(image_id):
    with db() as conn:
        image = conn.execute("SELECT filename FROM category_images WHERE id=?", (image_id,)).fetchone()
        if image:
            conn.execute("DELETE FROM category_images WHERE id=?", (image_id,))
    if image:
        remove_uploaded_image(image["filename"])
        flash("Снимката е изтрита.")
    return redirect(url_for("admin_dashboard"))


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
        filenames = [row[0] for row in conn.execute("SELECT filename FROM category_images WHERE service_id=?", (service_id,))]
        conn.execute("DELETE FROM services WHERE id=?", (service_id,))
    for filename in filenames:
        remove_uploaded_image(filename)
    flash("Услугата е изтрита.")
    return redirect(url_for("admin_dashboard"))


if __name__ == "__main__":
    app.run(host=os.environ.get("HOST", "127.0.0.1"), port=int(os.environ.get("PORT", "5000")), debug=False)
