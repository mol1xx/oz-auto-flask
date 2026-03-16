Flask-проект каталога автосервисов

1. Создай и активируй venv:
   python -m venv .venv
   .venv\Scripts\activate

2. Установи зависимости:
   pip install -r requirements.txt

3. Загрузи стартовые данные в SQLite:
   python seed.py

4. Запусти сайт:
   python app.py

5. Открой в браузере:
   http://127.0.0.1:5000

Что важно:
- База создаётся как файл database.db в корне проекта.
- Данные лежат в data/companies.json.
- Если меняешь JSON, снова запускай python seed.py.
- Это MVP. Для маркетплейса потом понадобятся отдельные таблицы услуг, заявок и симптомов.
