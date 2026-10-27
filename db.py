# db.py
import json
import logging
import re
import sqlite3
import time
from contextlib import contextmanager

from config import DB_PATH

logger = logging.getLogger(__name__)


class DuplicateActNumberError(ValueError):
    """Номер акта уже занят в пределах объекта."""


def pos_sort_key(pos_str):
    if not pos_str:
        return (999999,)
    try:
        return tuple(int(x) for x in pos_str.split("."))
    except ValueError:
        return (999999,)


def get_conn():
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 30000")
    return conn


@contextmanager
def db_conn():
    """Соединение с гарантированным commit/rollback/close."""
    conn = get_conn()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS objects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            customer TEXT,
            gen_contractor TEXT,
            gen_person_post TEXT,
            gen_person TEXT,
            gen_short TEXT,
            tech_post TEXT,
            tech_place TEXT,
            tech_name TEXT,
            tech_short TEXT,
            author_post TEXT,
            author_place TEXT,
            author_name TEXT,
            author_short TEXT,
            project_firm TEXT,
            project_date TEXT
        )
    """)

    cur.execute("PRAGMA table_info(objects)")
    obj_cols = {r["name"] for r in cur.fetchall()}
    for col, coltype in [
        ("subgen_person_post", "TEXT"),
        ("subgen_person", "TEXT"),
        ("subgen_short", "TEXT"),
        ("subgen_firm", "TEXT"),
    ]:
        if col not in obj_cols:
            cur.execute(f"ALTER TABLE objects ADD COLUMN {col} {coltype}")

    cur.execute("""
        CREATE TABLE IF NOT EXISTS positions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            object_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            position_number TEXT,
            FOREIGN KEY (object_id) REFERENCES objects(id) ON DELETE CASCADE
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS work_types (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE
        )
    """)

    # ---------- КАТЕГОРИИ МАТЕРИАЛОВ ----------
    cur.execute("""
        CREATE TABLE IF NOT EXISTS material_categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            sort_order INTEGER DEFAULT 0
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS materials (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            object_id INTEGER,
            name TEXT NOT NULL,
            quality_doc TEXT,
            work_types TEXT,
            category_id INTEGER,
            FOREIGN KEY (object_id) REFERENCES objects(id) ON DELETE CASCADE,
            FOREIGN KEY (category_id) REFERENCES material_categories(id) ON DELETE SET NULL
        )
    """)

    cur.execute("PRAGMA table_info(materials)")
    mat_cols = {r["name"] for r in cur.fetchall()}
    if "category_id" not in mat_cols:
        cur.execute("ALTER TABLE materials ADD COLUMN category_id INTEGER")
        print("🔧 Миграция materials: добавлена колонка category_id")

    cur.execute("""
        CREATE TABLE IF NOT EXISTS acts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            object_id INTEGER NOT NULL,
            position_id INTEGER,
            act_number TEXT NOT NULL,
            act_date TEXT,
            start_date TEXT,
            end_date TEXT,
            work_full TEXT,
            materials_used TEXT,
            file_path TEXT,
            sheets TEXT,
            section TEXT,
            cipher TEXT,
            work_type_name TEXT,
            work_name TEXT,
            position_number TEXT,
            materials_data TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cur.execute("PRAGMA table_info(acts)")
    existing = {r["name"] for r in cur.fetchall()}
    for col, coltype in [
        ("sheets", "TEXT"),
        ("section", "TEXT"),
        ("cipher", "TEXT"),
        ("work_type_name", "TEXT"),
        ("work_name", "TEXT"),
        ("position_number", "TEXT"),
        ("materials_data", "TEXT"),
        ("status", "TEXT DEFAULT 'ready'"),
        ("draft_step", "TEXT"),
        ("draft_data", "TEXT"),
    ]:
        if col not in existing:
            cur.execute(f"ALTER TABLE acts ADD COLUMN {col} {coltype}")

    cur.execute("UPDATE acts SET status = 'ready' " "WHERE status IS NULL OR status = ''")

    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_acts_status
        ON acts(status)
    """)
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_acts_object_status
        ON acts(object_id, status)
    """)

    # Черновики специально не входят в индекс: их номер может совпасть с
    # готовым актом до момента подтверждения/удаления черновика.
    try:
        cur.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_acts_object_number_unique
            ON acts(object_id, act_number)
            WHERE status IN ('ready', 'printed', 'archived')
        """)
    except sqlite3.IntegrityError as exc:
        logger.error(
            "Не удалось создать уникальный индекс номеров актов: %s. "
            "Проверьте дубли в таблице acts.",
            exc,
        )

    # Состояние FSM храним в SQLite, чтобы незавершённый сценарий пережил
    # перезапуск бота. Данные — JSON.
    cur.execute("""
        CREATE TABLE IF NOT EXISTS fsm_states (
            bot_id INTEGER NOT NULL,
            chat_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            thread_id INTEGER NOT NULL DEFAULT 0,
            business_connection_id TEXT NOT NULL DEFAULT '',
            destiny TEXT NOT NULL DEFAULT 'default',
            state TEXT,
            data TEXT NOT NULL DEFAULT '{}',
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (
                bot_id, chat_id, user_id, thread_id,
                business_connection_id, destiny
            )
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS drawings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            object_id INTEGER,
            position_number TEXT,
            section TEXT,
            cipher TEXT,
            file_path TEXT
        )
    """)

    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_drawings_lookup
        ON drawings(object_id, position_number, section)
    """)

    # ---------- ЦИКЛЫ ----------
    cur.execute("""
        CREATE TABLE IF NOT EXISTS cycles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            description TEXT,
            is_default INTEGER DEFAULT 0,
            owner_tg_id INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cur.execute("PRAGMA table_info(cycles)")
    cycle_cols = {r["name"] for r in cur.fetchall()}
    if "owner_tg_id" not in cycle_cols:
        cur.execute("ALTER TABLE cycles ADD COLUMN owner_tg_id INTEGER")
        print("🔧 Миграция cycles: добавлена колонка owner_tg_id")

    cur.execute("""
        CREATE TABLE IF NOT EXISTS cycle_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cycle_id INTEGER NOT NULL,
            order_num INTEGER NOT NULL,
            work_type TEXT NOT NULL,
            name_template TEXT,
            section_hint TEXT,
            sheets_hint TEXT,
            materials_hint TEXT,
            FOREIGN KEY (cycle_id) REFERENCES cycles(id) ON DELETE CASCADE
        )
    """)

    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_cycle_items_cycle
        ON cycle_items(cycle_id, order_num)
    """)

    # ---------- СЕРТИФИКАТЫ ----------
    # Старая схема содержала user_id. Переносим данные, а не удаляем таблицу.
    cur.execute("PRAGMA table_info(certificates)")
    cert_cols = {r["name"] for r in cur.fetchall()}
    legacy_certificates = bool(cert_cols and "user_id" in cert_cols)

    if legacy_certificates:
        print("🔧 Миграция certificates: переношу данные без user_id")
        cur.execute("ALTER TABLE certificates RENAME TO certificates_legacy")

    cur.execute("""
        CREATE TABLE IF NOT EXISTS certificates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            material_id INTEGER NOT NULL,
            number TEXT NOT NULL,
            date_from TEXT,
            notes TEXT,
            doc_type TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (material_id) REFERENCES materials(id) ON DELETE CASCADE
        )
    """)

    if legacy_certificates:

        def cert_col(name, default="NULL"):
            return name if name in cert_cols else default

        total = cur.execute("SELECT COUNT(*) FROM certificates_legacy").fetchone()[0]
        cur.execute(f"""
            INSERT INTO certificates
                (id, material_id, number, date_from, notes, doc_type, created_at)
            SELECT
                id,
                material_id,
                number,
                {cert_col("date_from")},
                {cert_col("notes")},
                {cert_col("doc_type")},
                {cert_col("created_at", "CURRENT_TIMESTAMP")}
            FROM certificates_legacy
            WHERE material_id IN (SELECT id FROM materials)
        """)
        moved = cur.rowcount
        skipped = total - moved
        if skipped:
            print(
                f"⚠️ Не перенесено сертификатов с несуществующим материалом: "
                f"{skipped}. Старая таблица сохранена как certificates_legacy."
            )
        else:
            cur.execute("DROP TABLE certificates_legacy")
        print(f"✅ Перенесено сертификатов: {moved}")

    cur.execute("PRAGMA table_info(certificates)")
    cert_cols2 = {r["name"] for r in cur.fetchall()}
    if cert_cols2 and "doc_type" not in cert_cols2:
        cur.execute("ALTER TABLE certificates ADD COLUMN doc_type TEXT")
        print("🔧 Миграция certificates: добавлена колонка doc_type")

    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_certificates_material
        ON certificates(material_id)
    """)

    # ---------- АВТОРСКИЙ НАДЗОР ПО ОБЪЕКТУ ----------
    cur.execute("""
        CREATE TABLE IF NOT EXISTS object_author_supervision (
            object_id INTEGER NOT NULL,
            work_type TEXT NOT NULL,
            PRIMARY KEY (object_id, work_type),
            FOREIGN KEY (object_id) REFERENCES objects(id) ON DELETE CASCADE
        )
    """)

    conn.commit()
    conn.close()
    print(f"✅ БД инициализирована: {DB_PATH}")


# =====================================================================
#  ОБЪЕКТЫ
# =====================================================================


def get_all_objects():
    conn = get_conn()
    rows = conn.execute("SELECT * FROM objects ORDER BY name").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_object(object_id):
    conn = get_conn()
    row = conn.execute("SELECT * FROM objects WHERE id = ?", (object_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def add_object(data: dict) -> int:
    conn = get_conn()
    cur = conn.cursor()
    fields = ", ".join(data.keys())
    placeholders = ", ".join("?" for _ in data)
    cur.execute(f"INSERT INTO objects ({fields}) VALUES ({placeholders})", tuple(data.values()))
    new_id = cur.lastrowid
    conn.commit()
    conn.close()
    return new_id


def update_object(object_id, **fields):
    if not fields:
        return
    allowed = {
        "name",
        "customer",
        "gen_contractor",
        "gen_person_post",
        "gen_person",
        "gen_short",
        "subgen_person_post",
        "subgen_person",
        "subgen_short",
        "subgen_firm",
        "tech_post",
        "tech_place",
        "tech_name",
        "tech_short",
        "author_post",
        "author_place",
        "author_name",
        "author_short",
        "project_firm",
        "project_date",
    }
    to_update = {k: v for k, v in fields.items() if k in allowed}
    if not to_update:
        return
    set_clause = ", ".join(f"{k} = ?" for k in to_update)
    values = list(to_update.values()) + [object_id]
    conn = get_conn()
    conn.execute(f"UPDATE objects SET {set_clause} WHERE id = ?", values)
    conn.commit()
    conn.close()


def get_object_author_supervision(object_id):
    conn = get_conn()
    rows = conn.execute(
        "SELECT work_type FROM object_author_supervision " "WHERE object_id = ? ORDER BY work_type",
        (object_id,),
    ).fetchall()
    conn.close()
    return [r["work_type"] for r in rows]


def add_object_author_supervision(object_id, work_type):
    conn = get_conn()
    try:
        conn.execute(
            "INSERT OR IGNORE INTO object_author_supervision "
            "(object_id, work_type) VALUES (?, ?)",
            (object_id, work_type),
        )
        conn.commit()
    finally:
        conn.close()


def remove_object_author_supervision(object_id, work_type):
    conn = get_conn()
    conn.execute(
        "DELETE FROM object_author_supervision " "WHERE object_id = ? AND work_type = ?",
        (object_id, work_type),
    )
    conn.commit()
    conn.close()


def is_author_supervision(object_id, work_type):
    if not work_type:
        return False
    conn = get_conn()
    row = conn.execute(
        "SELECT 1 FROM object_author_supervision " "WHERE object_id = ? AND work_type = ? LIMIT 1",
        (object_id, work_type),
    ).fetchone()
    conn.close()
    return row is not None


# =====================================================================
#  ПОЗИЦИИ
# =====================================================================


def get_positions_for_object(object_id):
    conn = get_conn()
    rows = conn.execute("SELECT * FROM positions WHERE object_id = ?", (object_id,)).fetchall()
    conn.close()
    result = [dict(r) for r in rows]
    result.sort(
        key=lambda p: (pos_sort_key(p.get("position_number") or ""), (p.get("name") or "").lower())
    )
    return result


def get_position(position_id):
    conn = get_conn()
    row = conn.execute("SELECT * FROM positions WHERE id = ?", (position_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def add_position(object_id, name, position_number):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO positions (object_id, name, position_number) VALUES (?, ?, ?)",
        (object_id, name, position_number),
    )
    new_id = cur.lastrowid
    conn.commit()
    conn.close()
    return new_id


# =====================================================================
#  ТИПЫ РАБОТ
# =====================================================================


def get_all_work_types():
    conn = get_conn()
    rows = conn.execute("SELECT * FROM work_types ORDER BY name").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def add_work_type(name):
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute("INSERT INTO work_types (name) VALUES (?)", (name,))
        new_id = cur.lastrowid
        conn.commit()
        conn.close()
        return new_id, True
    except sqlite3.IntegrityError:
        conn.close()
        return None, False


# =====================================================================
#  КАТЕГОРИИ МАТЕРИАЛОВ
# =====================================================================


def get_all_material_categories():
    conn = get_conn()
    rows = conn.execute("SELECT * FROM material_categories ORDER BY sort_order, name").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_material_category(cat_id):
    conn = get_conn()
    row = conn.execute("SELECT * FROM material_categories WHERE id = ?", (cat_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def add_material_category(name, sort_order=0):
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute(
            "INSERT INTO material_categories (name, sort_order) VALUES (?, ?)", (name, sort_order)
        )
        new_id = cur.lastrowid
        conn.commit()
        conn.close()
        return new_id, True
    except sqlite3.IntegrityError:
        conn.close()
        return None, False


def update_material_category(cat_id, name=None, sort_order=None):
    parts, values = [], []
    if name is not None:
        parts.append("name = ?")
        values.append(name)
    if sort_order is not None:
        parts.append("sort_order = ?")
        values.append(sort_order)
    if not parts:
        return True
    values.append(cat_id)
    conn = get_conn()
    try:
        conn.execute(f"UPDATE material_categories SET {', '.join(parts)} WHERE id = ?", values)
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()


def delete_material_category(cat_id, force=False):
    """force=False: удаляем только если пустая.
    force=True: материалы становятся 'без категории'."""
    conn = get_conn()
    cnt = conn.execute(
        "SELECT COUNT(*) FROM materials WHERE category_id = ?", (cat_id,)
    ).fetchone()[0]
    if cnt > 0 and not force:
        conn.close()
        return False
    if cnt > 0:
        conn.execute("UPDATE materials SET category_id = NULL WHERE category_id = ?", (cat_id,))
    conn.execute("DELETE FROM material_categories WHERE id = ?", (cat_id,))
    conn.commit()
    conn.close()
    return True


def count_materials_in_category(category_id):
    conn = get_conn()
    if category_id is None:
        cnt = conn.execute("SELECT COUNT(*) FROM materials WHERE category_id IS NULL").fetchone()[0]
    else:
        cnt = conn.execute(
            "SELECT COUNT(*) FROM materials WHERE category_id = ?", (category_id,)
        ).fetchone()[0]
    conn.close()
    return cnt


def get_categories_with_counts(object_id=None):
    """Список категорий с количеством материалов.
    object_id: учитываем только материалы объекта (или общие NULL)."""
    conn = get_conn()
    if object_id is not None:
        rows = conn.execute(
            """
            SELECT c.id, c.name, c.sort_order,
                   (SELECT COUNT(*) FROM materials m
                    WHERE m.category_id = c.id
                    AND (m.object_id = ? OR m.object_id IS NULL)) AS cnt
            FROM material_categories c
            ORDER BY c.sort_order, c.name
        """,
            (object_id,),
        ).fetchall()
        total = conn.execute(
            "SELECT COUNT(*) FROM materials " "WHERE object_id = ? OR object_id IS NULL",
            (object_id,),
        ).fetchone()[0]
    else:
        rows = conn.execute("""
            SELECT c.id, c.name, c.sort_order,
                   (SELECT COUNT(*) FROM materials m
                    WHERE m.category_id = c.id) AS cnt
            FROM material_categories c
            ORDER BY c.sort_order, c.name
        """).fetchall()
        total = conn.execute("SELECT COUNT(*) FROM materials").fetchone()[0]
    conn.close()
    result = []
    for r in rows:
        d = dict(r)
        d["count"] = d.pop("cnt", 0)
        result.append(d)
    return result, total


# =====================================================================
#  МАТЕРИАЛЫ
# =====================================================================


def get_materials_for_object(object_id, work_type=None, category_id=None):
    """Материалы объекта (или общие NULL).
    work_type: подходящие по work_types — в начале списка.
    category_id: фильтр по категории (None — все).
    """
    conn = get_conn()
    if category_id is not None:
        rows = conn.execute(
            """
            SELECT m.*, c.name AS category_name
            FROM materials m
            LEFT JOIN material_categories c ON c.id = m.category_id
            WHERE (m.object_id = ? OR m.object_id IS NULL)
              AND m.category_id = ?
            ORDER BY m.name
        """,
            (object_id, category_id),
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT m.*, c.name AS category_name
            FROM materials m
            LEFT JOIN material_categories c ON c.id = m.category_id
            WHERE m.object_id = ? OR m.object_id IS NULL
            ORDER BY COALESCE(c.sort_order, 9999), c.name, m.name
        """,
            (object_id,),
        ).fetchall()
    conn.close()
    result = [dict(r) for r in rows]

    if work_type:
        wt_lower = work_type.strip().lower()

        def is_match(m):
            raw = (m.get("work_types") or "").lower()
            parts = [p.strip() for p in raw.split("|") if p.strip()]
            return any(wt_lower == p or wt_lower in p for p in parts)

        matched = [m for m in result if is_match(m)]
        others = [m for m in result if not is_match(m)]
        result = matched + others

    return result


def get_all_materials_with_categories():
    conn = get_conn()
    rows = conn.execute("""
        SELECT m.*, c.name AS category_name
        FROM materials m
        LEFT JOIN material_categories c ON c.id = m.category_id
        ORDER BY COALESCE(c.sort_order, 9999), c.name, m.name
    """).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_all_materials():
    conn = get_conn()
    rows = conn.execute("SELECT * FROM materials ORDER BY name").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_material(material_id):
    conn = get_conn()
    row = conn.execute(
        """
        SELECT m.*, c.name AS category_name
        FROM materials m
        LEFT JOIN material_categories c ON c.id = m.category_id
        WHERE m.id = ?
    """,
        (material_id,),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def add_material(name, quality_doc="", object_id=None, work_types="", category_id=None):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO materials "
        "(object_id, name, quality_doc, work_types, category_id) "
        "VALUES (?, ?, ?, ?, ?)",
        (object_id, name, quality_doc, work_types, category_id),
    )
    new_id = cur.lastrowid
    conn.commit()
    conn.close()
    return new_id


def update_material(material_id, **fields):
    if not fields:
        return
    allowed = {"name", "quality_doc", "work_types", "object_id", "category_id"}
    to_update = {k: v for k, v in fields.items() if k in allowed}
    if not to_update:
        return
    set_clause = ", ".join(f"{k} = ?" for k in to_update)
    values = list(to_update.values()) + [material_id]
    conn = get_conn()
    conn.execute(f"UPDATE materials SET {set_clause} WHERE id = ?", values)
    conn.commit()
    conn.close()


def delete_material(material_id):
    conn = get_conn()
    conn.execute("DELETE FROM materials WHERE id = ?", (material_id,))
    conn.commit()
    conn.close()


def move_material_to_category(material_id, category_id):
    """category_id=None или 0 → без категории."""
    if category_id in (None, 0):
        category_id = None
    conn = get_conn()
    conn.execute("UPDATE materials SET category_id = ? WHERE id = ?", (category_id, material_id))
    conn.commit()
    conn.close()


def find_materials_by_hint(object_id, hint):
    if not hint:
        return []
    substrings = [s.strip().lower() for s in hint.split("|") if s.strip()]
    if not substrings:
        return []
    materials = get_materials_for_object(object_id)
    result = []
    for m in materials:
        name_lower = (m.get("name") or "").lower()
        if all(s in name_lower for s in substrings):
            result.append(m["id"])
    return result


# =====================================================================
#  СЕРТИФИКАТЫ
# =====================================================================


def get_certificates_for_material(material_id, limit=10):
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM certificates WHERE material_id = ? " "ORDER BY created_at DESC LIMIT ?",
        (material_id, limit),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def add_certificate(material_id, number, date_from=None, notes=None, doc_type=None):
    last_err = None
    for attempt in range(5):
        try:
            conn = get_conn()
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO certificates "
                "(material_id, number, date_from, notes, doc_type) "
                "VALUES (?, ?, ?, ?, ?)",
                (material_id, number, date_from, notes, doc_type),
            )
            new_id = cur.lastrowid
            conn.commit()
            conn.close()
            return new_id
        except sqlite3.OperationalError as e:
            last_err = e
            if "locked" in str(e).lower():
                time.sleep(0.5 * (attempt + 1))
                continue
            raise
    raise last_err


def delete_certificate(cert_id):
    conn = get_conn()
    conn.execute("DELETE FROM certificates WHERE id = ?", (cert_id,))
    conn.commit()
    conn.close()


# =====================================================================
#  АКТЫ
# =====================================================================


def get_next_act_number(object_id):
    conn = get_conn()
    row = conn.execute(
        "SELECT act_number FROM acts WHERE object_id = ? "
        "ORDER BY CAST(act_number AS INTEGER) DESC LIMIT 1",
        (object_id,),
    ).fetchone()
    conn.close()
    if row:
        try:
            return str(int(row["act_number"]) + 1)
        except ValueError:
            return "1"
    return "1"


def act_number_exists(object_id, act_number, exclude_act_id=None):
    """Проверяет, занят ли номер акта в пределах объекта."""
    with db_conn() as conn:
        if exclude_act_id:
            row = conn.execute(
                "SELECT 1 FROM acts WHERE object_id = ? AND act_number = ? " "AND id != ? LIMIT 1",
                (object_id, str(act_number), exclude_act_id),
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT 1 FROM acts WHERE object_id = ? AND act_number = ? " "LIMIT 1",
                (object_id, str(act_number)),
            ).fetchone()
    return row is not None


def get_recent_acts(object_id=None, limit=10):
    with db_conn() as conn:
        if object_id:
            rows = conn.execute(
                "SELECT * FROM acts WHERE object_id = ? AND status != 'draft' "
                "ORDER BY created_at DESC LIMIT ?",
                (object_id, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM acts WHERE status != 'draft' " "ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
    return [dict(r) for r in rows]


def get_act(act_id):
    with db_conn() as conn:
        row = conn.execute("SELECT * FROM acts WHERE id = ?", (act_id,)).fetchone()
    return dict(row) if row else None


def _is_duplicate_act_error(exc: sqlite3.IntegrityError) -> bool:
    text = str(exc).lower()
    return (
        "unique constraint failed: acts.object_id, acts.act_number" in text
        or "idx_acts_object_number_unique" in text
    )


def save_act(
    object_id,
    position_id,
    act_number,
    act_date,
    start_date,
    end_date,
    work_full,
    file_path,
    sheets="",
    section="",
    cipher="",
    work_type_name="",
    work_name="",
    position_number="",
    materials_data="",
    status="ready",
):
    last_err = None
    for attempt in range(5):
        try:
            with db_conn() as conn:
                cur = conn.cursor()
                cur.execute(
                    """INSERT INTO acts
                       (object_id, position_id, act_number, act_date,
                        start_date, end_date, work_full, file_path,
                        sheets, section, cipher,
                        work_type_name, work_name, position_number,
                        materials_data, status)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        object_id,
                        position_id,
                        act_number,
                        act_date,
                        start_date,
                        end_date,
                        work_full,
                        file_path,
                        sheets,
                        section,
                        cipher,
                        work_type_name,
                        work_name,
                        position_number,
                        materials_data,
                        status,
                    ),
                )
                return cur.lastrowid
        except sqlite3.IntegrityError as exc:
            if _is_duplicate_act_error(exc):
                raise DuplicateActNumberError(
                    f"Акт №{act_number} уже существует у этого объекта"
                ) from exc
            raise
        except sqlite3.OperationalError as e:
            last_err = e
            if "locked" in str(e).lower():
                time.sleep(0.5 * (attempt + 1))
                continue
            raise
    raise last_err


def update_act(act_id, **fields):
    if not fields:
        return
    allowed = {
        "act_number",
        "act_date",
        "start_date",
        "end_date",
        "work_full",
        "work_name",
        "file_path",
        "sheets",
        "section",
        "cipher",
        "materials_data",
        "position_id",
        "position_number",
        "work_type_name",
        "status",
        "draft_step",
        "draft_data",
    }
    to_update = {k: v for k, v in fields.items() if k in allowed}
    if not to_update:
        return
    set_clause = ", ".join(f"{k} = ?" for k in to_update)
    values = list(to_update.values()) + [act_id]

    last_err = None
    for attempt in range(5):
        try:
            with db_conn() as conn:
                conn.execute(f"UPDATE acts SET {set_clause} WHERE id = ?", values)
            return
        except sqlite3.IntegrityError as exc:
            if _is_duplicate_act_error(exc):
                raise DuplicateActNumberError(
                    f"Акт №{to_update.get('act_number', '')} уже существует " "у этого объекта"
                ) from exc
            raise
        except sqlite3.OperationalError as e:
            last_err = e
            if "locked" in str(e).lower():
                time.sleep(0.5 * (attempt + 1))
                continue
            raise
    raise last_err


def delete_act(act_id):
    with db_conn() as conn:
        conn.execute("DELETE FROM acts WHERE id = ?", (act_id,))


def set_act_status(act_id, status):
    with db_conn() as conn:
        conn.execute("UPDATE acts SET status = ? WHERE id = ?", (status, act_id))


def get_acts_by_status(object_id, status, limit=200):
    with db_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM acts WHERE object_id = ? AND status = ? "
            "ORDER BY CAST(act_number AS INTEGER) DESC LIMIT ?",
            (object_id, status, limit),
        ).fetchall()
    return [dict(r) for r in rows]


def get_act_status_counts(object_id):
    with db_conn() as conn:
        rows = conn.execute(
            "SELECT status, COUNT(*) AS cnt FROM acts " "WHERE object_id = ? GROUP BY status",
            (object_id,),
        ).fetchall()
    result = {"draft": 0, "ready": 0, "printed": 0, "archived": 0}
    for r in rows:
        key = r["status"] or "ready"
        result[key] = r["cnt"]
    return result


def get_acts_for_object(object_id, limit=5000, include_drafts=True):
    """Все акты объекта для поиска, экспорта и пакетной печати."""
    sql = "SELECT * FROM acts WHERE object_id = ?"
    params: list = [object_id]
    if not include_drafts:
        sql += " AND status != 'draft'"
    sql += " ORDER BY CAST(act_number AS INTEGER), created_at"
    sql += " LIMIT ?"
    params.append(max(1, int(limit)))
    with db_conn() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [dict(r) for r in rows]


def _materials_key(raw):
    """Каноническое представление материалов для сравнения дублей."""
    if not raw:
        return ()
    try:
        items = json.loads(raw)
    except (TypeError, ValueError):
        return str(raw or "")
    if not isinstance(items, list):
        return str(raw or "")
    normalized = []
    for item in items:
        if isinstance(item, dict):
            normalized.append(
                (
                    str(item.get("id") or ""),
                    str(item.get("name") or ""),
                    str(item.get("cert") or ""),
                )
            )
        else:
            normalized.append(str(item))
    return tuple(sorted(normalized))


def find_duplicate_act(
    object_id,
    work_type_name,
    work_name,
    position_number,
    start_date,
    end_date,
    exclude_act_id=None,
    work_full=None,
    materials_json=None,
):
    """Ищет готовый акт с полностью совпадающими ключевыми данными."""
    sql = (
        "SELECT * FROM acts WHERE object_id = ? AND status != 'draft' "
        "AND COALESCE(work_type_name, '') = ? "
        "AND COALESCE(work_name, '') = ? "
        "AND COALESCE(position_number, '') = ? "
        "AND COALESCE(start_date, '') = ? "
        "AND COALESCE(end_date, '') = ?"
    )
    params = [
        object_id,
        work_type_name or "",
        work_name or "",
        position_number or "",
        start_date or "",
        end_date or "",
    ]
    if work_full is not None:
        sql += " AND COALESCE(work_full, '') = ?"
        params.append(work_full or "")
    if exclude_act_id:
        sql += " AND id != ?"
        params.append(exclude_act_id)
    sql += " ORDER BY CAST(act_number AS INTEGER)"
    with db_conn() as conn:
        rows = conn.execute(sql, params).fetchall()
    materials_key = _materials_key(materials_json) if materials_json is not None else None
    for row in rows:
        if materials_key is None or _materials_key(row["materials_data"]) == materials_key:
            return dict(row)
    return None


def _normalise_date_key(raw):
    """'01.10.2026 г.' -> (2026, 10, 1); пусто/мусор -> None."""
    match = re.search(r"(\d{1,2})[./-](\d{1,2})[./-](\d{4})", str(raw or ""))
    if not match:
        return None
    try:
        d, m, y = (int(x) for x in match.groups())
        return (y, m, d)
    except ValueError:
        return None


def get_acts_before_date(object_id, cutoff_date):
    """Акты с датой акта ДО указанной (cutoff — 'ДД.ММ.ГГГГ')."""
    cutoff = _normalise_date_key(cutoff_date)
    if not cutoff:
        return []
    acts = get_acts_for_object(object_id, limit=100000, include_drafts=False)
    result = []
    for act in acts:
        if (act.get("status") or "ready") == "archived":
            continue
        key = _normalise_date_key(act.get("act_date"))
        if key and key < cutoff:
            result.append(act)
    return result


def get_acts_in_period(object_id, start_date=None, end_date=None):
    """Акты с датой акта в заданном периоде (границы включительно)."""
    start = _normalise_date_key(start_date) if start_date else None
    end = _normalise_date_key(end_date) if end_date else None
    if start_date and start is None:
        return []
    if end_date and end is None:
        return []
    if start and end and start > end:
        return []
    acts = get_acts_for_object(object_id, limit=100000, include_drafts=False)
    result = []
    for act in acts:
        if (act.get("status") or "ready") == "archived":
            continue
        key = _normalise_date_key(act.get("act_date"))
        if not key:
            continue
        if start and key < start:
            continue
        if end and key > end:
            continue
        result.append(act)
    return result


def save_draft_act(object_id, act_number, draft_step, draft_data):
    with db_conn() as conn:
        cur = conn.execute(
            """INSERT INTO acts
               (object_id, act_number, status, draft_step, draft_data,
                act_date, start_date, end_date, work_full, file_path)
               VALUES (?, ?, 'draft', ?, ?, '', '', '', '', '')""",
            (object_id, act_number, draft_step, draft_data),
        )
        return cur.lastrowid


def update_draft_act(act_id, draft_step, draft_data):
    with db_conn() as conn:
        conn.execute(
            "UPDATE acts SET draft_step = ?, draft_data = ? WHERE id = ?",
            (draft_step, draft_data, act_id),
        )


# =====================================================================
#  ДАТЫ / ВЫБОРКИ
# =====================================================================


def get_acts_dates(limit=20, object_id=None, statuses=("ready", "printed")):
    conn = get_conn()
    placeholders = ",".join("?" for _ in statuses)
    if object_id:
        rows = conn.execute(
            f"SELECT act_date, COUNT(*) AS cnt FROM acts "
            f"WHERE object_id = ? AND status IN ({placeholders}) "
            f"AND act_date IS NOT NULL AND act_date != '' "
            f"GROUP BY act_date ORDER BY act_date DESC LIMIT ?",
            (object_id, *statuses, limit),
        ).fetchall()
    else:
        rows = conn.execute(
            f"SELECT act_date, COUNT(*) AS cnt FROM acts "
            f"WHERE status IN ({placeholders}) "
            f"AND act_date IS NOT NULL AND act_date != '' "
            f"GROUP BY act_date ORDER BY act_date DESC LIMIT ?",
            (*statuses, limit),
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_acts_by_date(act_date, object_id=None):
    conn = get_conn()
    if object_id:
        rows = conn.execute(
            "SELECT * FROM acts WHERE act_date = ? AND object_id = ? "
            "AND status != 'draft' "
            "ORDER BY CAST(act_number AS INTEGER)",
            (act_date, object_id),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM acts WHERE act_date = ? AND status != 'draft' "
            "ORDER BY CAST(act_number AS INTEGER)",
            (act_date,),
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# =====================================================================
#  ПРОЕКТНАЯ ДОКУМЕНТАЦИЯ
# =====================================================================


def get_sections_for_position(object_id, position_number):
    conn = get_conn()
    if position_number:
        rows = conn.execute(
            "SELECT DISTINCT section FROM drawings "
            "WHERE object_id = ? AND position_number = ? "
            "ORDER BY section",
            (object_id, position_number),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT DISTINCT section FROM drawings "
            "WHERE object_id = ? "
            "AND (position_number = '' OR position_number IS NULL) "
            "ORDER BY section",
            (object_id,),
        ).fetchall()
    conn.close()
    return [r["section"] for r in rows]


def get_drawing(object_id, position_number, section):
    conn = get_conn()
    if position_number:
        row = conn.execute(
            "SELECT * FROM drawings "
            "WHERE object_id = ? AND position_number = ? AND section = ? "
            "LIMIT 1",
            (object_id, position_number, section),
        ).fetchone()
    else:
        row = conn.execute(
            "SELECT * FROM drawings "
            "WHERE object_id = ? "
            "AND (position_number = '' OR position_number IS NULL) "
            "AND section = ? LIMIT 1",
            (object_id, section),
        ).fetchone()
    conn.close()
    return dict(row) if row else None


def get_drawings_for_position(object_id, position_number):
    conn = get_conn()
    if position_number:
        rows = conn.execute(
            "SELECT * FROM drawings "
            "WHERE object_id = ? AND position_number = ? "
            "ORDER BY section, cipher",
            (object_id, position_number),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM drawings "
            "WHERE object_id = ? "
            "AND (position_number = '' OR position_number IS NULL) "
            "ORDER BY section, cipher",
            (object_id,),
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_drawings_by_section(object_id, position_number, section):
    conn = get_conn()
    if position_number:
        rows = conn.execute(
            "SELECT * FROM drawings "
            "WHERE object_id = ? AND position_number = ? AND section = ? "
            "ORDER BY cipher",
            (object_id, position_number, section),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM drawings "
            "WHERE object_id = ? "
            "AND (position_number = '' OR position_number IS NULL) "
            "AND section = ? "
            "ORDER BY cipher",
            (object_id, section),
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def add_drawing(object_id, position_number, section, cipher, file_path):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO drawings "
        "(object_id, position_number, section, cipher, file_path) "
        "VALUES (?, ?, ?, ?, ?)",
        (object_id, position_number, section, cipher, file_path),
    )
    new_id = cur.lastrowid
    conn.commit()
    conn.close()
    return new_id


def clear_drawings_for_object(object_id):
    """Удаляет чертежи только одного объекта."""
    conn = get_conn()
    conn.execute("DELETE FROM drawings WHERE object_id = ?", (object_id,))
    conn.commit()
    conn.close()


def clear_drawings():
    """Удаляет чертежи всех объектов (для полной пересборки)."""
    conn = get_conn()
    conn.execute("DELETE FROM drawings")
    conn.commit()
    conn.close()


# =====================================================================
#  ЦИКЛЫ
# =====================================================================


def get_all_cycles():
    conn = get_conn()
    rows = conn.execute("""
        SELECT c.*,
               (SELECT COUNT(*) FROM cycle_items WHERE cycle_id = c.id) AS items_count
        FROM cycles c
        ORDER BY c.is_default DESC, c.owner_tg_id IS NOT NULL, c.name
    """).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_cycles_for_user(owner_tg_id):
    conn = get_conn()
    rows = conn.execute(
        """
        SELECT c.*,
               (SELECT COUNT(*) FROM cycle_items WHERE cycle_id = c.id) AS items_count
        FROM cycles c
        WHERE c.owner_tg_id IS NULL OR c.owner_tg_id = ?
        ORDER BY c.is_default DESC, c.owner_tg_id IS NOT NULL, c.name
    """,
        (owner_tg_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_cycle(cycle_id):
    conn = get_conn()
    row = conn.execute("SELECT * FROM cycles WHERE id = ?", (cycle_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_cycle_items(cycle_id):
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM cycle_items WHERE cycle_id = ? ORDER BY order_num", (cycle_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_cycle_item(item_id):
    conn = get_conn()
    row = conn.execute("SELECT * FROM cycle_items WHERE id = ?", (item_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def add_cycle(name, description=None, is_default=0, owner_tg_id=None):
    conn = get_conn()
    cur = conn.cursor()
    base_name = name
    suffix = 0
    while True:
        try:
            cur.execute(
                "INSERT INTO cycles (name, description, is_default, owner_tg_id) "
                "VALUES (?, ?, ?, ?)",
                (name, description, is_default, owner_tg_id),
            )
            conn.commit()
            new_id = cur.lastrowid
            conn.close()
            return new_id
        except sqlite3.IntegrityError:
            suffix += 1
            name = f"{base_name} ({suffix})"


def update_cycle(cycle_id, name=None, description=None):
    parts, values = [], []
    if name is not None:
        parts.append("name = ?")
        values.append(name)
    if description is not None:
        parts.append("description = ?")
        values.append(description)
    if not parts:
        return True
    values.append(cycle_id)
    conn = get_conn()
    try:
        conn.execute(f"UPDATE cycles SET {', '.join(parts)} WHERE id = ?", values)
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()


def add_cycle_item(
    cycle_id,
    order_num,
    work_type,
    name_template="{common}",
    section_hint=None,
    sheets_hint=None,
    materials_hint=None,
):
    conn = get_conn()
    conn.execute(
        """
        INSERT INTO cycle_items
        (cycle_id, order_num, work_type, name_template,
         section_hint, sheets_hint, materials_hint)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """,
        (cycle_id, order_num, work_type, name_template, section_hint, sheets_hint, materials_hint),
    )
    conn.commit()
    conn.close()


def update_cycle_item(item_id, work_type=None, name_template=None):
    parts, values = [], []
    if work_type is not None:
        parts.append("work_type = ?")
        values.append(work_type)
    if name_template is not None:
        parts.append("name_template = ?")
        values.append(name_template)
    if not parts:
        return
    values.append(item_id)
    conn = get_conn()
    conn.execute(f"UPDATE cycle_items SET {', '.join(parts)} WHERE id = ?", values)
    conn.commit()
    conn.close()


def delete_cycle_item(item_id):
    conn = get_conn()
    row = conn.execute("SELECT cycle_id FROM cycle_items WHERE id = ?", (item_id,)).fetchone()
    if not row:
        conn.close()
        return
    cycle_id = row["cycle_id"]
    conn.execute("DELETE FROM cycle_items WHERE id = ?", (item_id,))
    remaining = conn.execute(
        "SELECT id FROM cycle_items WHERE cycle_id = ? ORDER BY order_num", (cycle_id,)
    ).fetchall()
    for i, r in enumerate(remaining, start=1):
        conn.execute("UPDATE cycle_items SET order_num = ? WHERE id = ?", (i, r["id"]))
    conn.commit()
    conn.close()


def move_cycle_item(item_id, direction):
    conn = get_conn()
    cur = conn.cursor()
    item = cur.execute("SELECT * FROM cycle_items WHERE id = ?", (item_id,)).fetchone()
    if not item:
        conn.close()
        return False
    cycle_id = item["cycle_id"]
    order_num = item["order_num"]
    neighbor_num = order_num - 1 if direction == "up" else order_num + 1
    neighbor = cur.execute(
        "SELECT id FROM cycle_items WHERE cycle_id = ? AND order_num = ?", (cycle_id, neighbor_num)
    ).fetchone()
    if not neighbor:
        conn.close()
        return False
    cur.execute("UPDATE cycle_items SET order_num = ? WHERE id = ?", (neighbor_num, item["id"]))
    cur.execute("UPDATE cycle_items SET order_num = ? WHERE id = ?", (order_num, neighbor["id"]))
    conn.commit()
    conn.close()
    return True


def delete_cycle(cycle_id, owner_tg_id=None):
    conn = get_conn()
    if owner_tg_id is not None:
        conn.execute("DELETE FROM cycles WHERE id = ? AND owner_tg_id = ?", (cycle_id, owner_tg_id))
    else:
        conn.execute("DELETE FROM cycles WHERE id = ?", (cycle_id,))
    conn.commit()
    conn.close()


def clear_default_cycles():
    conn = get_conn()
    conn.execute("DELETE FROM cycles WHERE is_default = 1")
    conn.commit()
    conn.close()


def copy_cycle_for_user(source_cycle_id, owner_tg_id, new_name=None):
    src = get_cycle(source_cycle_id)
    if not src:
        return None
    name = new_name or f"{src['name']} (моя версия)"
    new_id = add_cycle(
        name,
        src.get("description") or "",
        is_default=0,
        owner_tg_id=owner_tg_id,
    )
    if not new_id:
        return None
    for it in get_cycle_items(source_cycle_id):
        add_cycle_item(
            new_id,
            it["order_num"],
            it["work_type"],
            it.get("name_template") or "{common}",
            it.get("section_hint"),
            it.get("sheets_hint"),
            it.get("materials_hint"),
        )
    return new_id


def render_cycle_name(template, common_part):
    if not template:
        template = "{common}"
    try:
        return template.format(common=common_part).strip()
    except (KeyError, IndexError):
        return template


STEP_TEMPLATES = [
    "{common}",
    "под устройство {common}",
    "под фундамент {common}",
    "пазух {common}",
    "стен {common}",
    "днища {common}",
]


if __name__ == "__main__":
    init_db()
