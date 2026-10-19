# Вътрешни ремонти

Леко Python 3 уеб приложение за фирма за вътрешни ремонти. Включва публичен ценоразпис по категории, администраторски панел и директен WhatsApp бутон. Данните се пазят локално в SQLite (`repairs.sqlite3`), а примерните услуги се добавят автоматично при първо стартиране. HTML шаблоните са в `templates/`, а CSS ресурсите — в `static/`.

## Стартиране

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

Изображенията в `static/images/` се оптимизират до WebP с `python scripts/optimize_images.py` (изходните файлове се запазват). Настрой `SITE_URL` в `.env` с публичния адрес на сайта, за да сочат canonical адресът, `sitemap.xml` и `robots.txt` към правилния домейн; sitemap-ът включва публичната начална страница, а админ адресите са изключени от обхождане.

Настройките се зареждат от `.env` в папката на проекта. Копирай `.env.example` като `.env`, после смени `ADMIN_PASSWORD` и `SECRET_KEY`. `.env` е локален файл и не се качва в Git.

Отвори http://127.0.0.1:5000. Администрацията е на `/admin`; след вход избери „Към сайта“ или отвори `/admin/dashboard`.

В администрацията можеш да смениш името, юридическото име, ЕИК, адреса за картата, района и WhatsApp телефона. Номерът се въвежда в международен формат само с цифри, например `359888123456`. Можеш да добавяш, преименуваш и изтриваш категории, както и да редактираш услугите, описанията и цените. Празна цена се показва като „По договаряне“.

По подразбиране приложението слуша само на локалната машина; за публичен сървър използвай WSGI сървър и HTTPS.

## Подготовка за SuperHosting.bg / cPanel

1. В cPanel отвори **Setup Python App** и създай приложение с директория `vatreshni-remonti` (извън `public_html`), избран домейн и URI. Избери версия Python, съвместима със зависимостите.
2. Задай startup file `passenger_wsgi.py` и entry point `application`. Файлът е в корена на проекта и експортира Flask приложението за Passenger.
3. Създай `.env` ръчно в директорията на приложението на сървъра. Добави `SECRET_KEY`, силна `ADMIN_PASSWORD`, `SITE_URL` с публичния HTTPS адрес и при нужда `WHATSAPP_PHONE`. Този файл не се качва чрез Git deployment.
4. Инсталирай зависимостите от `requirements.txt` във виртуалната среда на Python приложението през Setup Python App.
5. В cPanel **Git Version Control** клонирай хранилището отделно от App Directory и deploy-ни commit-а. `.cpanel.yml` копира кода, шаблоните, статичните файлове и скриптовете в `$HOME/vatreshni-remonti/`, после създава Passenger restart marker. Настрой друга стойност на `DEPLOYPATH` в `.cpanel.yml`, ако App Directory е различна.
6. След deploy провери сайта и `/robots.txt`, `/sitemap.xml`, както и входа към `/admin`.

`.cpanel.yml` нарочно не копира `.env` или `repairs.sqlite3`: настройките и базата остават в App Directory при следващи deploy-и. Първото зареждане създава SQLite базата автоматично. При push директно към cPanel-managed Git repository cPanel може да стартира deployment автоматично; при repository, което се обновява от външен remote, използвай **Update from Remote** и после **Deploy HEAD Commit**.
