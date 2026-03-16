import json
from pathlib import Path
from difflib import SequenceMatcher


BASE_DIR = Path(__file__).resolve().parent
SYMPTOMS_PATH = BASE_DIR / "data" / "symptoms.json"


def load_symptoms():
    with open(SYMPTOMS_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def normalize_text(text):
    return (text or "").strip().lower().replace("ё", "е")


def similarity(a, b):
    return SequenceMatcher(None, normalize_text(a), normalize_text(b)).ratio()


def find_best_symptom(user_text, symptoms):
    user_text_norm = normalize_text(user_text)

    best_match = None
    best_score = 0.0

    for symptom in symptoms:
        title_score = similarity(user_text_norm, symptom["title"])
        if title_score > best_score:
            best_score = title_score
            best_match = symptom

        for alias in symptom.get("aliases", []):
            alias_score = similarity(user_text_norm, alias)
            if alias_score > best_score:
                best_score = alias_score
                best_match = symptom

            if user_text_norm in normalize_text(alias) or normalize_text(alias) in user_text_norm:
                if alias_score < 0.95:
                    alias_score = 0.95
                if alias_score > best_score:
                    best_score = alias_score
                    best_match = symptom

    if best_score < 0.45:
        return None, best_score

    return best_match, best_score


def find_question(symptom, question_id):
    for question in symptom.get("questions", []):
        if question["id"] == question_id:
            return question
    return None


def rule_matches(rule_if, answers):
    for key, value in rule_if.items():
        if answers.get(key) != value:
            return False
    return True


def evaluate_symptom(symptom, answers):
    matched_rules = []

    for rule in symptom.get("rules", []):
        if rule_matches(rule.get("if", {}), answers):
            matched_rules.append(rule)

    if matched_rules:
        categories = []
        causes = []
        urgencies = []

        for rule in matched_rules:
            if rule.get("cause"):
                causes.append(rule["cause"])
            for cat in rule.get("recommended_categories", []):
                if cat not in categories:
                    categories.append(cat)
            if rule.get("urgency"):
                urgencies.append(rule["urgency"])

        urgency = highest_urgency(urgencies) if urgencies else "medium"

        return {
            "matched": True,
            "causes": causes,
            "recommended_categories": categories,
            "urgency": urgency,
            "possible_causes": symptom.get("possible_causes", [])
        }

    return {
        "matched": False,
        "causes": symptom.get("possible_causes", []),
        "recommended_categories": [],
        "urgency": "medium",
        "possible_causes": symptom.get("possible_causes", [])
    }


def highest_urgency(values):
    order = {
        "low": 1,
        "medium": 2,
        "high": 3,
        "critical": 4
    }
    best = "low"
    best_score = 1

    for value in values:
        score = order.get(value, 2)
        if score > best_score:
            best_score = score
            best = value

    return best


def urgency_label(value):
    mapping = {
        "low": "Низкая",
        "medium": "Средняя",
        "high": "Высокая",
        "critical": "Критическая"
    }
    return mapping.get(value, "Средняя")