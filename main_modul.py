from __future__ import annotations
 
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
 
from flask import Flask, flash, g, jsonify, redirect, render_template, request, url_for
 
BASE_DIR = Path(__file__).resolve().parent
DATABASE = BASE_DIR / "applications.db"
 
app = Flask(__name__)
app.config["SECRET_KEY"] = "demo-secret-key"
app.config["DATABASE"] = str(DATABASE)
 
STATUSES = ["Новая", "В работе", "Нужно уточнение", "Согласована", "Отклонена", "Закрыта"]
SOURCES = ["Сайт", "Телефон", "Электронная почта", "Партнёр"]
TYPES = ["Подключение услуги", "Консультация", "Технический вопрос", "Изменение условий", "Документы"]
MANAGERS = ["А. В. Орлова", "М. С. Петров", "Е. Н. Соколова", "И. К. Смирнов"]
 
 
def get_db() -> sqlite3.Connection:
    if "db" not in g:
        g.db = sqlite3.connect(app.config["DATABASE"])
        g.db.row_factory = sqlite3.Row
    return g.db
 
 
@app.teardown_appcontext
def close_db(error: BaseException | None = None) -> None:
    db = g.pop("db", None)
    if db is not None:
        db.close()
 
 
def init_db() -> None:
    db = sqlite3.connect(app.config["DATABASE"])
    db.executescript(
        """
        DROP TABLE IF EXISTS applications;
        CREATE TABLE applications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            client_name TEXT NOT NULL,
            company TEXT NOT NULL,
            phone TEXT NOT NULL,
            email TEXT NOT NULL,
            request_type TEXT NOT NULL,
            source TEXT NOT NULL,
            status TEXT NOT NULL,
            priority TEXT NOT NULL,
            manager TEXT NOT NULL,
            amount REAL NOT NULL DEFAULT 0,
            closed_at TEXT,
            comment TEXT NOT NULL DEFAULT ''
        );
        """
    )
 
    clients = [
        ("Иванов Андрей Сергеевич", "ООО «Альфа-Сервис»"),
        ("Кузнецова Марина Олеговна", "ИП Кузнецова М. О."),
        ("Смирнов Павел Викторович", "ООО «Городские системы»"),
        ("Соколова Елена Николаевна", "АО «Вектор»"),
        ("Орлов Дмитрий Игоревич", "ООО «ТехноПлюс»"),
        ("Васильева Анна Романовна", "ИП Васильева А. Р."),
        ("Петров Максим Сергеевич", "ООО «Север»"),
        ("Михайлова Ольга Андреевна", "ООО «Новые решения»"),
        ("Фёдоров Кирилл Алексеевич", "АО «Контур»"),
        ("Николаева Ирина Денисовна", "ООО «Баланс»"),
        ("Алексеев Роман Ильич", "ИП Алексеев Р. И."),
        ("Захарова Светлана Юрьевна", "ООО «Перспектива»"),
    ]
    priorities = ["Обычный", "Высокий", "Обычный", "Низкий"]
    today = date(2026, 7, 15)
    rows: list[tuple[Any, ...]] = []
    for i in range(36):
        person, company = clients[i % len(clients)]
        created = today - timedelta(days=(i * 2) % 44)
        status = STATUSES[i % len(STATUSES)]
        closed_at = None
        if status in {"Согласована", "Отклонена", "Закрыта"}:
            closed_at = (created + timedelta(days=1 + (i % 6))).isoformat()
        rows.append(
            (
                created.isoformat(),
                person,
                company,
                f"+7 900 {100 + i:03d}-{20 + i:02d}-{30 + i:02d}",
                f"client{i + 1}@example.test",
                TYPES[i % len(TYPES)],
                SOURCES[(i + 1) % len(SOURCES)],
                status,
                priorities[i % len(priorities)],
                MANAGERS[i % len(MANAGERS)],
                float(25000 + (i % 8) * 15000),
                closed_at,
                "Демонстрационная запись. Персональные данные не являются реальными.",
            )
        )
    db.executemany(
        """
        INSERT INTO applications (
            created_at, client_name, company, phone, email, request_type,
            source, status, priority, manager, amount, closed_at, comment
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )
    db.commit()
    db.close()
 
 
def dashboard_metrics(db: sqlite3.Connection) -> dict[str, Any]:
    total = db.execute("SELECT COUNT(*) FROM applications").fetchone()[0]
    new_count = db.execute("SELECT COUNT(*) FROM applications WHERE status='Новая'").fetchone()[0]
    active = db.execute("SELECT COUNT(*) FROM applications WHERE status IN ('В работе','Нужно уточнение')").fetchone()[0]
    approved = db.execute("SELECT COUNT(*) FROM applications WHERE status='Согласована'").fetchone()[0]
    avg_days = db.execute(
        """
        SELECT ROUND(AVG(julianday(closed_at) - julianday(created_at)), 1)
        FROM applications WHERE closed_at IS NOT NULL
        """
    ).fetchone()[0] or 0
    total_amount = db.execute("SELECT SUM(amount) FROM applications WHERE status='Согласована'").fetchone()[0] or 0
    return {
        "total": total,
        "new_count": new_count,
        "active": active,
        "approved": approved,
        "avg_days": avg_days,
        "total_amount": total_amount,
    }
 
 
@app.route("/")
def dashboard() -> str:
    db = get_db()
    metrics = dashboard_metrics(db)
    recent = db.execute("SELECT * FROM applications ORDER BY created_at DESC, id DESC LIMIT 8").fetchall()
    status_rows = db.execute(
        "SELECT status, COUNT(*) AS count FROM applications GROUP BY status ORDER BY count DESC"
    ).fetchall()
    return render_template("dashboard.html", metrics=metrics, recent=recent, status_rows=status_rows)
 
 
@app.route("/applications")
def applications() -> str:
    db = get_db()
    status = request.args.get("status", "")
    source = request.args.get("source", "")
    query = request.args.get("q", "").strip()
    sql = "SELECT * FROM applications WHERE 1=1"
    params: list[Any] = []
    if status:
        sql += " AND status = ?"
        params.append(status)
    if source:
        sql += " AND source = ?"
        params.append(source)
    if query:
        sql += " AND (client_name LIKE ? OR company LIKE ? OR email LIKE ?)"
        wildcard = f"%{query}%"
        params.extend([wildcard, wildcard, wildcard])
    sql += " ORDER BY created_at DESC, id DESC"
    rows = db.execute(sql, params).fetchall()
    return render_template(
        "applications.html",
        applications=rows,
        statuses=STATUSES,
        sources=SOURCES,
        selected_status=status,
        selected_source=source,
        query=query,
    )
 
 
@app.route("/applications/new", methods=["GET", "POST"])
def new_application() -> str:
    if request.method == "POST":
        required = ["client_name", "company", "phone", "email", "request_type", "source"]
        missing = [name for name in required if not request.form.get(name, "").strip()]
        if missing:
            flash("Заполните обязательные поля.", "error")
        else:
            db = get_db()
            db.execute(
                """
                INSERT INTO applications (
                    created_at, client_name, company, phone, email, request_type,
                    source, status, priority, manager, amount, comment
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 'Новая', ?, ?, ?, ?)
                """,
                (
                    datetime.now().date().isoformat(),
                    request.form["client_name"].strip(),
                    request.form["company"].strip(),
                    request.form["phone"].strip(),
                    request.form["email"].strip(),
                    request.form["request_type"],
                    request.form["source"],
                    request.form.get("priority", "Обычный"),
                    request.form.get("manager", MANAGERS[0]),
                    float(request.form.get("amount", "0") or 0),
                    request.form.get("comment", "").strip(),
                ),
            )
            db.commit()
            flash("Заявка добавлена.", "success")
            return redirect(url_for("applications"))
    return render_template("new_application.html", types=TYPES, sources=SOURCES, managers=MANAGERS)
 
 
@app.route("/analytics")
def analytics() -> str:
    db = get_db()
    metrics = dashboard_metrics(db)
    by_status = db.execute(
        "SELECT status AS label, COUNT(*) AS value FROM applications GROUP BY status ORDER BY value DESC"
    ).fetchall()
    by_source = db.execute(
        "SELECT source AS label, COUNT(*) AS value FROM applications GROUP BY source ORDER BY value DESC"
    ).fetchall()
    by_type = db.execute(
        "SELECT request_type AS label, COUNT(*) AS value FROM applications GROUP BY request_type ORDER BY value DESC"
    ).fetchall()
    by_manager = db.execute(
        "SELECT manager AS label, COUNT(*) AS value FROM applications GROUP BY manager ORDER BY value DESC"
    ).fetchall()
    return render_template(
        "analytics.html",
        metrics=metrics,
        by_status=by_status,
        by_source=by_source,
        by_type=by_type,
        by_manager=by_manager,
    )
 
 
@app.route("/api/analytics")
def analytics_api():
    db = get_db()
    return jsonify(
        metrics=dashboard_metrics(db),
        status=[dict(row) for row in db.execute("SELECT status, COUNT(*) count FROM applications GROUP BY status")],
        source=[dict(row) for row in db.execute("SELECT source, COUNT(*) count FROM applications GROUP BY source")],
    )
 
 
if __name__ == "__main__":
    if not DATABASE.exists():
        init_db()
    app.run(host="127.0.0.1", port=5000, debug=False)
