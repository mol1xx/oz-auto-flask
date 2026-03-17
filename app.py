import sqlite3
from pathlib import Path
from flask import Flask, render_template, request, abort, redirect, url_for, session

from diagnostic_engine import (
    load_symptoms,
    find_best_symptom,
    evaluate_symptom,
    urgency_label,
)

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "database.db"

app = Flask(__name__)
app.secret_key = "change-this-secret-key"


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def build_filters():
    return {
        "q": request.args.get("q", "").strip(),
        "city": request.args.get("city", "").strip(),
        "district": request.args.get("district", "").strip(),
        "metro": request.args.get("metro", "").strip(),
        "category": request.args.get("category", "").strip(),
        "sort": request.args.get("sort", "rating_desc").strip(),
        "has_phone": request.args.get("has_phone") == "1",
        "has_site": request.args.get("has_site") == "1",
        "only_active": request.args.get("only_active") == "1",
    }


def get_filter_options(selected_city_slug=None):
    conn = get_connection()
    cur = conn.cursor()

    cities = cur.execute("""
        SELECT DISTINCT city_slug, city_name
        FROM company
        WHERE city_slug IS NOT NULL AND TRIM(city_slug) != ''
        ORDER BY city_name
    """).fetchall()

    districts_sql = """
        SELECT DISTINCT district
        FROM company
        WHERE district IS NOT NULL AND TRIM(district) != ''
    """
    districts_params = []

    metro_sql = """
        SELECT DISTINCT metro_station
        FROM company
        WHERE metro_station IS NOT NULL AND TRIM(metro_station) != ''
    """
    metro_params = []

    if selected_city_slug:
        districts_sql += " AND city_slug = ?"
        metro_sql += " AND city_slug = ?"
        districts_params.append(selected_city_slug)
        metro_params.append(selected_city_slug)

    districts_sql += " ORDER BY district"
    metro_sql += " ORDER BY metro_station"

    districts = cur.execute(districts_sql, districts_params).fetchall()
    metro_stations = cur.execute(metro_sql, metro_params).fetchall()

    categories = cur.execute("""
        SELECT DISTINCT category
        FROM company
        WHERE category IS NOT NULL AND TRIM(category) != ''
        ORDER BY category
    """).fetchall()

    conn.close()

    return cities, districts, metro_stations, categories


def get_companies(filters=None, recommended_categories=None, limit=None):
    conn = get_connection()
    cur = conn.cursor()

    sql = "SELECT * FROM company WHERE 1=1"
    params = []

    if recommended_categories:
        placeholders = ",".join("?" for _ in recommended_categories)
        sql += f" AND category IN ({placeholders})"
        params.extend(recommended_categories)

    if filters:
        if filters["q"]:
            sql += """
                AND (
                    name LIKE ?
                    OR category LIKE ?
                    OR subcategory LIKE ?
                    OR city_name LIKE ?
                    OR district LIKE ?
                    OR metro_station LIKE ?
                    OR address LIKE ?
                    OR description LIKE ?
                )
            """
            like_value = f"%{filters['q']}%"
            params.extend([like_value] * 8)

        if filters["city"]:
            sql += " AND city_slug = ?"
            params.append(filters["city"])

        if filters["district"]:
            sql += " AND district = ?"
            params.append(filters["district"])

        if filters["metro"]:
            sql += " AND metro_station = ?"
            params.append(filters["metro"])

        if filters["category"]:
            sql += " AND category = ?"
            params.append(filters["category"])

        if filters["has_phone"]:
            sql += " AND phone IS NOT NULL AND TRIM(phone) != ''"

        if filters["has_site"]:
            sql += " AND website IS NOT NULL AND TRIM(website) != ''"

        if filters["only_active"]:
            sql += " AND is_active = 1"

        if filters["sort"] == "name_asc":
            sql += " ORDER BY name COLLATE NOCASE ASC"
        elif filters["sort"] == "reviews_desc":
            sql += " ORDER BY reviews_count DESC, rating DESC"
        else:
            sql += " ORDER BY rating DESC, reviews_count DESC"
    else:
        sql += " ORDER BY rating DESC, reviews_count DESC"

    if limit:
        sql += f" LIMIT {int(limit)}"

    companies = cur.execute(sql, params).fetchall()
    total_count = cur.execute("SELECT COUNT(*) FROM company").fetchone()[0]

    conn.close()
    return companies, total_count


@app.route("/")
def index():
    filters = build_filters()
    companies, total_count = get_companies(filters=filters)

    cities, districts, metro_stations, categories = get_filter_options(
        selected_city_slug=filters["city"] or None
    )

    symptoms = load_symptoms()
    popular_symptoms = symptoms[:6]

    return render_template(
        "index.html",
        companies=companies,
        total_count=total_count,
        filtered_count=len(companies),
        filters=filters,
        cities=cities,
        districts=districts,
        metro_stations=metro_stations,
        categories=categories,
        popular_symptoms=popular_symptoms,
    )


@app.route("/company/<slug>")
def company_page(slug):
    conn = get_connection()
    company = conn.execute(
        "SELECT * FROM company WHERE slug = ?",
        (slug,)
    ).fetchone()
    conn.close()

    if not company:
        abort(404)

    return render_template("company.html", company=company)


@app.route("/diagnosis/start", methods=["POST"])
def diagnosis_start():
    user_text = request.form.get("user_text", "").strip()
    symptoms = load_symptoms()

    symptom, score = find_best_symptom(user_text, symptoms)

    if not symptom:
        session.pop("diagnosis", None)
        return render_template(
            "diagnosis_result.html",
            diagnosis_failed=True,
            user_text=user_text,
            symptom=None,
            result=None,
            matched_companies=[],
            urgency_label_text=None,
        )

    session["diagnosis"] = {
        "user_text": user_text,
        "symptom_slug": symptom["slug"],
        "answers": {},
        "current_question_index": 0
    }

    return redirect(url_for("diagnosis_step"))


@app.route("/diagnosis/step", methods=["GET", "POST"])
def diagnosis_step():
    diagnosis = session.get("diagnosis")
    if not diagnosis:
        return redirect(url_for("index"))

    symptoms = load_symptoms()
    symptom = next((s for s in symptoms if s["slug"] == diagnosis["symptom_slug"]), None)

    if not symptom:
        session.pop("diagnosis", None)
        return redirect(url_for("index"))

    if request.method == "POST":
        question_id = request.form.get("question_id")
        answer = request.form.get("answer", "").strip()

        if question_id and answer:
            diagnosis["answers"][question_id] = answer
            diagnosis["current_question_index"] += 1
            session["diagnosis"] = diagnosis

    current_index = diagnosis["current_question_index"]
    questions = symptom.get("questions", [])

    if current_index >= len(questions):
        return redirect(url_for("diagnosis_result"))

    question = questions[current_index]

    return render_template(
        "diagnosis_result.html",
        diagnosis_mode="question",
        symptom=symptom,
        question=question,
        answers=diagnosis["answers"]
    )


@app.route("/diagnosis/result")
def diagnosis_result():
    diagnosis = session.get("diagnosis")
    if not diagnosis:
        return redirect(url_for("index"))

    symptoms = load_symptoms()
    symptom = next((s for s in symptoms if s["slug"] == diagnosis["symptom_slug"]), None)

    if not symptom:
        session.pop("diagnosis", None)
        return redirect(url_for("index"))

    result = evaluate_symptom(symptom, diagnosis["answers"])
    matched_companies = []

    if result["recommended_categories"]:
        matched_companies, _ = get_companies(
            filters=None,
            recommended_categories=result["recommended_categories"],
            limit=12
        )

    return render_template(
        "diagnosis_result.html",
        diagnosis_mode="result",
        symptom=symptom,
        result=result,
        matched_companies=matched_companies,
        urgency_label_text=urgency_label(result["urgency"]),
        diagnosis_failed=False
    )


@app.route("/diagnosis/reset")
def diagnosis_reset():
    session.pop("diagnosis", None)
    return redirect(url_for("index"))


if __name__ == "__main__":
    print("APP DB PATH:", DB_PATH)
    app.run(debug=True)
