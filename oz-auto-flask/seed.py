import csv
import sqlite3
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "database.db"
CSV_PATH = BASE_DIR / "orekhovo_zuevo_auto_catalog.csv"


def safe_str(value, default=""):
    if value is None:
        return default
    return str(value).strip()


def safe_float(value, default=0.0):
    try:
        value = safe_str(value)
        if not value:
            return default
        return float(value.replace(",", "."))
    except (ValueError, TypeError):
        return default


def safe_int(value, default=0):
    try:
        value = safe_str(value)
        if not value:
            return default
        return int(float(value.replace(",", ".")))
    except (ValueError, TypeError):
        return default


def make_slug(text, fallback="company"):
    text = safe_str(text).lower()

    ru_to_lat = {
        "а": "a", "б": "b", "в": "v", "г": "g", "д": "d",
        "е": "e", "ё": "e", "ж": "zh", "з": "z", "и": "i",
        "й": "y", "к": "k", "л": "l", "м": "m", "н": "n",
        "о": "o", "п": "p", "р": "r", "с": "s", "т": "t",
        "у": "u", "ф": "f", "х": "h", "ц": "ts", "ч": "ch",
        "ш": "sh", "щ": "sch", "ъ": "", "ы": "y", "ь": "",
        "э": "e", "ю": "yu", "я": "ya"
    }

    result = []
    for ch in text:
        if ch in ru_to_lat:
            result.append(ru_to_lat[ch])
        elif ch.isalnum():
            result.append(ch)
        else:
            result.append("-")

    slug = "".join(result)
    while "--" in slug:
        slug = slug.replace("--", "-")
    slug = slug.strip("-")

    return slug or fallback


def ensure_table(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS company (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            slug TEXT NOT NULL UNIQUE,
            category TEXT,
            subcategory TEXT,
            district TEXT,
            address TEXT,
            phone TEXT,
            website TEXT,
            description TEXT,
            rating REAL DEFAULT 0,
            reviews_count INTEGER DEFAULT 0,
            is_active INTEGER DEFAULT 1,
            source_url TEXT,
            source_type TEXT
        )
    """)
    conn.commit()


def reset_table(conn):
    conn.execute("DROP TABLE IF EXISTS company")
    conn.commit()
    ensure_table(conn)


def import_csv(conn, csv_path):
    inserted = 0
    skipped = 0
    used_slugs = set()

    with open(csv_path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)

        for row in reader:
            name = safe_str(row.get("name"))
            if not name:
                skipped += 1
                continue

            category = safe_str(row.get("primary_category"))
            subcategory = safe_str(row.get("subcategory"))
            address = safe_str(row.get("address"))
            phone = safe_str(row.get("phone"))
            website = safe_str(row.get("website"))
            rating = safe_float(row.get("rating"), 0.0)
            reviews_count = safe_int(row.get("reviews_count"), 0)
            district = safe_str(row.get("district"))
            description = safe_str(row.get("notes"))
            source_url = safe_str(row.get("source_url"))
            source_type = safe_str(row.get("source_type"))
            status = safe_str(row.get("status")).lower()

            is_active = 1 if status in ("active", "open", "yes", "1", "true") else 0

            slug_base = make_slug(name)
            slug = slug_base
            counter = 2
            while slug in used_slugs:
                slug = f"{slug_base}-{counter}"
                counter += 1
            used_slugs.add(slug)

            conn.execute("""
                INSERT INTO company (
                    name,
                    slug,
                    category,
                    subcategory,
                    district,
                    address,
                    phone,
                    website,
                    description,
                    rating,
                    reviews_count,
                    is_active,
                    source_url,
                    source_type
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                name,
                slug,
                category,
                subcategory,
                district,
                address,
                phone,
                website,
                description,
                rating,
                reviews_count,
                is_active,
                source_url,
                source_type
            ))
            inserted += 1

    conn.commit()
    return inserted, skipped


def main():
    if not CSV_PATH.exists():
        raise FileNotFoundError(f"Не найден файл: {CSV_PATH}")

    conn = sqlite3.connect(DB_PATH)

    try:
        reset_table(conn)
        inserted, skipped = import_csv(conn, CSV_PATH)
        total = conn.execute("SELECT COUNT(*) FROM company").fetchone()[0]

        print("Импорт завершён.")
        print(f"Загружено: {inserted}")
        print(f"Пропущено: {skipped}")
        print(f"Всего в базе: {total}")
        print(f"База: {DB_PATH}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()