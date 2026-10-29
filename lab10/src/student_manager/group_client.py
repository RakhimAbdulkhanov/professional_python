import asyncio
import math
import urllib.parse
from collections.abc import Sequence
from typing import cast

import httpx


def _validate_options(
    group_ids: Sequence[int],
    base_url: str,
    timeout: float,
    retries: int,
    concurrency: int,
    backoff: float,
    client: httpx.AsyncClient | None,
) -> None:
    # перевіряємо параметри виклику
    if not isinstance(group_ids, Sequence) or isinstance(
        group_ids, (str, bytes, bytearray)
    ):
        raise TypeError("group_ids must be a sequence of positive integers")

    for gid in group_ids:
        if isinstance(gid, bool) or not isinstance(gid, int):
            raise TypeError(f"group_id must be an integer, got {gid!r}")
        if gid <= 0:
            raise ValueError(f"group_id must be positive, got {gid!r}")

    if not isinstance(base_url, str):
        raise TypeError("base_url must be a string")
    if not base_url.strip():
        raise ValueError("base_url must be a non-empty string")

    parsed = urllib.parse.urlsplit(base_url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ValueError(f"base_url must be a valid http/https URL, got {base_url!r}")

    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)):
        raise TypeError("timeout must be a number")
    if timeout <= 0:
        raise ValueError("timeout must be a positive number")

    if isinstance(retries, bool) or not isinstance(retries, int):
        raise TypeError("retries must be an integer")
    if retries < 0:
        raise ValueError("retries must be a non-negative integer")

    if isinstance(concurrency, bool) or not isinstance(concurrency, int):
        raise TypeError("concurrency must be an integer")
    if concurrency < 1:
        raise ValueError("concurrency must be an integer >= 1")

    if isinstance(backoff, bool) or not isinstance(backoff, (int, float)):
        raise TypeError("backoff must be a number")
    if backoff < 0:
        raise ValueError("backoff must be a non-negative number")

    if client is not None and not isinstance(client, httpx.AsyncClient):
        raise TypeError("client must be an httpx.AsyncClient instance or None")


def _validate_best_student(student: object) -> None:
    if student is None:
        return
    if not isinstance(student, dict):
        raise TypeError("Invalid best_student: expected StudentResponse or None")

    required_keys = {
        "student_id",
        "first_name",
        "last_name",
        "group_id",
        "group",
        "average_grade",
    }
    if not required_keys.issubset(student) or student.keys() - required_keys - {
        "email"
    }:
        raise ValueError("Invalid best_student fields")

    for field in ("student_id", "group_id"):
        value = student[field]
        if isinstance(value, bool) or not isinstance(value, int):
            raise TypeError(f"Invalid best_student {field}: expected integer")
        if value <= 0:
            raise ValueError(f"Invalid best_student {field}: must be positive")

    for field in ("first_name", "last_name", "group"):
        value = student[field]
        if not isinstance(value, str):
            raise TypeError(f"Invalid best_student {field}: expected string")
        if not value.strip():
            raise ValueError(f"Invalid best_student {field}: must not be blank")

    grade = student["average_grade"]
    if isinstance(grade, bool) or not isinstance(grade, (int, float)):
        raise TypeError("Invalid best_student average_grade: expected number")
    if not 0 <= grade <= 100:
        raise ValueError(
            "Invalid best_student average_grade: must be finite in [0, 100]"
        )

    email = student.get("email")
    if email is not None and not isinstance(email, str):
        raise TypeError("Invalid best_student email: expected string or None")


def _validate_schema(data: object, expected_group_id: int) -> dict[str, object]:
    # валідуємо структуру відповіді з сервера
    if not isinstance(data, dict):
        raise TypeError(
            f"Expected dict response for group {expected_group_id}, got {type(data).__name__}"
        )

    required_keys = {"group_id", "count", "average", "best_student"}
    if not required_keys.issubset(data.keys()):
        missing = required_keys - set(data.keys())
        raise ValueError(
            f"Missing required fields {missing} in group {expected_group_id} statistics"
        )

    gid = data["group_id"]
    if isinstance(gid, bool) or not isinstance(gid, int):
        raise TypeError(f"Invalid group_id type in response: {type(gid).__name__}")
    if gid != expected_group_id:
        raise ValueError(
            f"Mismatched group_id in response: {gid!r}, expected {expected_group_id}"
        )

    count = data["count"]
    if isinstance(count, bool) or not isinstance(count, int):
        raise TypeError(f"Invalid count type in response: {type(count).__name__}")
    if count < 0:
        raise ValueError(f"Invalid count in response: {count!r}")

    average = data["average"]
    if average is not None and (
        isinstance(average, bool) or not isinstance(average, (int, float))
    ):
        raise TypeError(f"Invalid average type in response: {type(average).__name__}")
    if isinstance(average, float) and not math.isfinite(average):
        raise ValueError("Invalid average in response: must be finite")

    _validate_best_student(data["best_student"])

    # вертаємо типізований словник зі збереженням значень
    return cast(dict[str, object], data)


async def _fetch_single_group(
    client: httpx.AsyncClient,
    base_url: str,
    group_id: int,
    semaphore: asyncio.Semaphore,
    timeout: float,
    retries: int,
    backoff: float,
) -> dict[str, object]:
    # робимо запит по окремій групі з обмеженням семафором та повторами
    url = f"{base_url.rstrip('/')}/groups/{group_id}/statistics"

    for attempt in range(retries + 1):
        try:
            async with semaphore:
                response = await client.get(url, timeout=timeout)
        except (httpx.TimeoutException, httpx.NetworkError):
            if attempt < retries:
                delay = min(backoff * (2**attempt), 10.0)
                await asyncio.sleep(delay)
                continue
            raise

        status = response.status_code
        if 200 <= status < 300:
            try:
                payload = cast(object, response.json())
            except Exception as exc:
                # битий json не повторюємо
                raise ValueError(
                    f"Malformed JSON response for group {group_id}"
                ) from exc

            return _validate_schema(payload, group_id)

        if status == 429 or (500 <= status < 600):
            # тимчасові помилки повторюємо
            if attempt < retries:
                delay = min(backoff * (2**attempt), 10.0)
                await asyncio.sleep(delay)
                continue
            response.raise_for_status()

        # постійні помилки 4xx або інші кидаємо негайно
        response.raise_for_status()

    # захисний випадок якщо вичерпались спроби
    raise RuntimeError(f"Retries exhausted for group {group_id}")


async def fetch_group_statistics(
    group_ids: Sequence[int],
    *,
    base_url: str,
    client: httpx.AsyncClient | None = None,
    timeout: float = 5.0,
    retries: int = 2,
    concurrency: int = 4,
    backoff: float = 0.05,
) -> list[dict[str, object]]:
    # завантажує статистику груп паралельно з контролем одночасності
    _validate_options(
        group_ids,
        base_url,
        timeout,
        retries,
        concurrency,
        backoff,
        client,
    )

    if not group_ids:
        return []

    owned_client = client is None
    http_client = client if client is not None else httpx.AsyncClient()
    semaphore = asyncio.Semaphore(concurrency)

    tasks: list[asyncio.Task[dict[str, object]]] = []
    try:
        for gid in group_ids:
            task = asyncio.create_task(
                _fetch_single_group(
                    http_client,
                    base_url,
                    gid,
                    semaphore,
                    timeout,
                    retries,
                    backoff,
                )
            )
            tasks.append(task)

        results = await asyncio.gather(*tasks)
        return list(results)
    except BaseException:
        # при помилці чи скасуванні скасовуємо залишок задач
        for task in tasks:
            if not task.done():
                task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        raise
    finally:
        # закриваємо тільки власний клієнт
        if owned_client:
            await http_client.aclose()
