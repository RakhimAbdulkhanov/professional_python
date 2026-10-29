# Student Manager

Навчальний проєкт з дисципліни «Професійний Python».
Варіант 1: система обліку студентів.

Автор: Абдулханов Абдул-Рахім, група ФеП-33.
Викладач: проф. Свелеба С. А.

## Можливості

- Додавання студента: ім'я, прізвище, група, середній бал.
- Перегляд списку та пошук за групою без урахування регістру.
- Визначення студента з найбільшим середнім балом.
- Обчислення середнього бала вибраної групи.
- Консольне меню, перевірка введення та демонстраційний режим.

Оцінка має бути числом від 0 до 100, текстові поля не можуть бути порожніми.
Для порожньої групи середній бал відсутній, а не дорівнює нулю.
Якщо кілька студентів мають однаковий найбільший бал, вибирається перший
у списку. Однакові імена дозволені, бо вони не є унікальними ідентифікаторами.

## Встановлення

Потрібен Python 3.11 або новіший. Для YAML-конфігурації використовується PyYAML;
він встановлюється разом із пакетом.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
```

Linux/macOS: для активації використовуйте `source .venv/bin/activate`.

Без активації у Windows можна виконувати команди через
`.\.venv\Scripts\python.exe`.

## Запуск

Інтерактивне меню з порожнім списком студентів:

```powershell
python -m student_manager.main
```

Готовий приклад із чотирма навчальними записами:

```powershell
python -m student_manager.main --demo
```

Після встановлення доступна також команда `student-manager --demo`.
Меню: `1` - додати, `2` - список, `3` - пошук за групою,
`4` - найкращий студент, `5` - середній бал групи, `0` - вихід.

У демонстраційному наборі група ФеП-33 має середній бал 88.07.
Найкраща студентка - Ірина Бондар із балом 95.20.
Це вигадані навчальні записи, не реальні персональні дані.

**Обмеження Lab 1:** записи зберігаються в пам'яті до завершення програми.
Збереження у файлах і базі даних передбачене наступними роботами.

## Перевірка

Базові тести попередніх робіт можна запускати через unittest. Повний suite
роботи 6 використовує pytest і pytest-cov із dev dependencies:

```powershell
python -m pip install -e ".[dev]"
python -m pytest --cov=student_manager --cov-branch --cov-report=term-missing --cov-report=html
python -m unittest discover -s tests -v
```

Поріг комбінованого покриття інструкцій і гілок - 80%. HTML-звіт створюється
локально в `htmlcov/` і не публікується. Окремо можна запустити
`python -m pytest tests/unit -v` або `python -m pytest tests/integration -v`.

Перевіряються модель, межі оцінок, порожні поля, пошук групи,
середній бал, найкращий студент і консольні сценарії.

## Структура

```text
src/student_manager/
    __init__.py   - версія пакета
    models.py     - Student і перевірка його полів
    services.py   - додавання, пошук і розрахунки
    main.py       - консольне меню та демонстрація
tests/            - автоматичні перевірки
lab1/task/        - завдання викладача
lab1/lab1_report.pdf - звіт
```

`pyproject.toml` описує пакет і консольну команду.
`src-layout` відділяє код пакета від звітів, завдань і тестів.
Імпорт `student_manager.main` не запускає меню завдяки перевірці `__name__`.

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
