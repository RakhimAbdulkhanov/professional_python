# Student Manager

## Description

Навчальний наскрізний проєкт з дисципліни «Професійний Python».
Варіант 1: система обліку студентів (packaging, configuration, Docker, REST API, CI/CD).

## Features

- Додавання студента: ім'я, прізвище, група, середній бал.
- Перегляд списку та пошук за групою без урахування регістру.
- Визначення студента з найбільшим середнім балом.
- Обчислення середнього бала вибраної групи.
- Перенесення студентів між групами.
- REST API на базі FastAPI з моніторингом працездатності (`/health`).
- Реляційне збереження даних у SQLite через SQLAlchemy ORM з міграціями Alembic.
- Контейнеризація в Docker з підтримкою volume для персистентності.
- Автоматизований CI/CD пайплайн на GitHub Actions.

## Requirements

- Python >= 3.11
- Docker (опціонально для контейнеризації)

## Installation

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
```

## Configuration

Конфігурація застосунку передається через змінні середовища (12-Factor App) за допомогою Pydantic Settings:
- `DATABASE_URL`: рядок підключення до БД (за замовчуванням `sqlite:///app.db` або `sqlite:////app/data/students.sqlite` у Docker)
- `ENVIRONMENT` / `APP_ENV`: поточне середовище (`development`, `test`, `production`)
- `LOG_LEVEL`: рівень логування (`DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`)

Зразок налаштувань наведено у файлі `.env.example`.

## Running locally

Запуск REST API через uvicorn:
```bash
uvicorn student_manager.api:app --host 127.0.0.1 --port 8000 --reload
```

Запуск інтерактивного консольного інтерфейсу:
```bash
student-manager --demo
```

## Running with Docker

Збірка Docker образу:
```bash
docker build -t student-manager:1.0 .
```

Запуск контейнера з підключенням volume для збереження даних:
```bash
docker run -d -p 8000:8000 -v student_data:/app/data -e ENVIRONMENT=production student-manager:1.0
```

Або за допомогою Docker Compose:
```bash
docker compose up -d
```

## API

Основні REST API ендпоінти:
- `GET /health` - перевірка працездатності сервісу та доступності БД
- `POST /groups` - створення академічної групи
- `GET /groups` - список груп
- `POST /students` - створення картки студента
- `GET /students` - фільтрація та список студентів
- `GET /students/{student_id}` - перегляд інформації про студента
- `GET /groups/{group_id}/students` - студенти вибраної групи
- `GET /groups/{group_id}/statistics` - розрахунок статистики групи (кількість, середній бал)
- `PATCH /students/{student_id}` - оновлення даних студента
- `DELETE /students/{student_id}` - видалення студента

Інтерактивна документація Swagger UI доступна за адресою `http://localhost:8000/docs`, а OpenAPI схема - за `http://localhost:8000/openapi.json`.

## Testing

Запуск повного набору тестів з перевіркою покриття (поріг 80%):
```bash
pytest --cov=student_manager --cov-branch --cov-report=term-missing
```

Перевірка статичної типізації та форматування:
```bash
mypy src
ruff check src tests
ruff format --check src tests
```

## Project structure

```text
├── .github/workflows/ci.yml  - GitHub Actions CI пайплайн
├── src/student_manager/      - основний код пакета
│   ├── api.py               - FastAPI застосунок та ендпоінти
│   ├── config.py            - конфігурація та налаштування Pydantic Settings
│   ├── database.py          - підключення до бази даних
│   ├── models.py            - доменні моделі даних
│   ├── repositories.py      - інтерфейси репозиторіїв
│   ├── services.py          - бізнес-логіка
│   └── main.py              - точка входу CLI
├── tests/                   - набір автоматичних тестів
├── migrations/              - міграції Alembic
├── Dockerfile               - багатоетапна збірка контейнера
├── docker-compose.yml       - запуск стеків контейнерів
├── pyproject.toml           - специфікація пакета та залежності
├── README.md                - документація
└── LICENSE                  - ліцензія MIT
```

## CI/CD

Автоматичний пайплайн GitHub Actions запускається на кожен push і pull request:
1. Lint (ruff check)
2. Format check (ruff format)
3. Type check (mypy)
4. Tests with coverage (pytest >= 80%)
5. Build package (wheel, sdist)
6. Smoke-test встановленого wheel у чистому віртуальному середовищі
7. Docker image build та перевірка запуску з persistent volume та non-root user

## Authors

Виконав: студент групи ФеП-33 Абдулханов Абдул-Рахім.
Викладач: проф. Свелеба С. А.

## Лабораторні роботи

| Робота | Тема | Матеріали |
|---|---|---|
| 1 | Організація професійного Python-проєкту та Git | [Завдання](lab1/task/Lab_01.docx), [звіт](lab1/lab1_report.pdf), [код](src/student_manager), [тести](tests) |
| 2 | Структури даних та функціональна декомпозиція | [Завдання](lab2/task/Lab_02_узгоджено_з_Lab_01.docx), [звіт](lab2/lab2_report.pdf), [аналітика](src/student_manager/analytics.py) |
| 3 | Ітератори, генератори та потокова обробка | [Завдання](lab3/task/Lab_03_узгоджено_з_Lab_01.docx), [звіт](lab3/lab3_report.pdf), [конвеєр](src/student_manager/streaming.py) |
| 4 | Професійне ООП та система типів | [Завдання](lab4/task/Lab_04_узгоджено_з_Lab_01.docx), [звіт](lab4/lab4_report.pdf), [реєстр](src/student_manager/registry.py) |
| 5 | Обробка помилок, файли та серіалізація | [Завдання](lab5/task/Lab_05_узгоджено_з_Lab_01.docx), [звіт](lab5/lab5_report.pdf), [імпорт та експорт](src/student_manager/reliable_io.py) |
| 6 | Автоматизоване тестування | [Завдання](lab6/task/Lab_06_узгоджено_з_Lab_01.docx), [звіт](lab6/lab6_report.pdf), [експерименти](lab6/experiments.py), [тести](tests) |
| 7 | Робота з базами даних у Python | [Завдання](lab7/task/Lab_07_узгоджено_з_Lab_01%20.docx), [звіт](lab7/lab7_report.pdf), [демо](src/student_manager/lab7_demo.py), [тести](tests) |
| 8 | Розробка REST API на FastAPI та асинхронного клієнта | [Завдання](lab8/task/Lab_08_узгоджено_з_Lab_01.docx), [звіт](lab8/lab8_report.pdf), [API](src/student_manager/api.py), [тести](tests) |
| 9 | Профілювання, оптимізація та паралельні обчислення | [Завдання](lab9/task/Lab_09_узгоджено_з_Lab_01.docx), [звіт](lab9/lab9_report.pdf), [модуль](src/student_manager/performance.py), [тести](tests) |
| 10 | Пакування, контейнеризація та CI/CD | [Завдання](lab10/task/Lab_10_узгоджено_з_Lab_01.docx), [звіт](lab10/lab10_report.pdf), [Dockerfile](Dockerfile), [CI](.github/workflows/ci.yml) |

Усі роботи продовжують один пакет. Стан першої роботи збережений у тегу `lab1`.

## Робота 6: автоматизоване тестування

`tests/unit/` перевіряє модель, оцінки, реєстр і взаємодію залежностей.
`tests/integration/` виконує справжній конвеєр CSV - валідація - JSON
у тимчасових каталогах. Fixtures, параметризація, `pytest.approx`,
`pytest.raises`, `monkeypatch` і Mock ізолюють сценарії. `AsyncStudentService`
завантажує студента через асинхронний інтерфейс репозиторію; тести
перевіряють `AsyncMock`, awaited calls і відсутність сповіщення після збою.

Окремі навчальні експерименти навмисно створюють слабкі та failing tests
в ізольованому каталозі. Вони не входять як failing cases до основного suite:

```powershell
python lab6/experiments.py --output .local_workflow/lab6/testing_experiments_results.json
```

## Робота 7: SQLite та SQLAlchemy

База містить таблиці `groups` і `students` зі зв'язком one-to-many.
Репозиторії виконують CRUD, пошук, фільтрацію та SQL-агрегації. Сервіс
керує commit/rollback; масове переведення студентів є атомарним.
Міграції Alembic створюють початкову схему, а потім додають nullable `email`.
Вони включені до wheel, тому демонстрація працює і без клонованого репозиторію.

```powershell
python -m student_manager.main --lab7 students.sqlite
student-manager --lab7 another_students.sqlite
python -m pytest tests/test_persistence.py tests/test_migrations.py tests/test_dbapi.py -v
```

Демонстрація створює нову SQLite-базу, додає вигадані записи, змінює оцінку,
переводить студента, перевіряє rollback і видалення. Наявний файл не перезаписує.
Для ручного керування міграціями в репозиторії використовуйте `alembic upgrade head`;
URL береться з `alembic.ini` або `DATABASE_URL`. Не задавайте production URL
для навчальних демонстрацій. Сесія репозиторію належить викликачеві;
після DB-level IntegrityError викликач має виконати rollback.

## Роботи 2-5

```powershell
python -m student_manager.main --lab2
python -m student_manager.main --lab3 lab3/task/students.csv
python -m student_manager.main --lab4
python -m student_manager.main --config lab5/task/config.yaml
```

Робота 2 додає унікальні групи, загальний середній бал, рейтинг, групування,
кількість студентів і словниковий індекс прізвищ. Індекс зберігає всіх
однофамільців. Фільтр бала тут використовує строге `>`.

Починаючи з роботи 3, CSV має точний заголовок:

```csv
student_id,first_name,last_name,group,average_grade
1,Олена,Коваль,ФеП-33,91.5
```

ID є додатним цілим числом; текстові поля непорожні, оцінка скінченна в межах
0-100. Потокові фільтри використовують `>=`. Перші N збігів зберігають порядок
джерела; top-N переглядає весь потік і обирає найбільші оцінки через heap.
Відкривайте файлові потоки через `with open_student_stream(...)`, особливо
для дострокового завершення. Повторний обхід потребує нового потоку.

Робота 4 додає `Group`, `Grade`, `AcademicRecord`, `StudentRegistry`, generic
repository, інтерфейс сповіщень і окремий сервіс звітів. Некоректне редагування
не змінює попередній запис. Репозиторій залишається в пам'яті.

Робота 5 читає YAML-шляхи відносно конфігурації. `skip_invalid: true` пропускає
помилкові записи з журналюванням; `false` зупиняється на першій помилці.
Лічильник valid враховує записи до фільтрації. JSON записується потоково
в тимчасовий файл поряд із цільовим; заміна відбувається лише після успіху.
Попередній результат залишається незмінним у разі помилки. Приклади містять
лише вигадані навчальні дані. Згенеровані output/log файли не публікуються.

### Експерименти та статична перевірка

```powershell
python -m student_manager.experiments lookup
python -m student_manager.streaming_experiments --work-dir .local_workflow/lab3/scratch --output .local_workflow/lab3/experiment_results.json
python -m student_manager.reliable_experiments
python -m pip install -e ".[dev]"
python -m mypy src
python -m ruff check src tests
python -m ruff format --check src tests
python -m unittest discover -s tests -v
```

Великі CSV створюються для експериментів локально. Час генерації не входить
у вимірювання. `tracemalloc` показує пік виділень Python, а не всю RAM процесу.
Час залежить від комп'ютера та навантаження; lazy обробка не гарантує прискорення.
