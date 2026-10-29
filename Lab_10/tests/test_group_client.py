import asyncio
import json
import unittest
from unittest.mock import patch

import httpx
import pytest

from student_manager.group_client import fetch_group_statistics


def student_payload(group_id: int = 1) -> dict[str, object]:
    return {
        "student_id": 7,
        "first_name": "Олена",
        "last_name": "Коваль",
        "group_id": group_id,
        "group": "ФеП-33",
        "average_grade": 94.5,
        "email": None,
    }


def fetch_payload(payload: dict[str, object]) -> list[dict[str, object]]:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, content=json.dumps(payload))

    async def run_client() -> list[dict[str, object]]:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            try:
                return await fetch_group_statistics(
                    [1],
                    base_url="http://testserver",
                    client=client,
                    retries=3,
                    backoff=0,
                )
            finally:
                assert not client.is_closed

    try:
        return asyncio.run(run_client())
    finally:
        assert calls == 1


@pytest.mark.parametrize("average", [float("nan"), float("inf"), -float("inf")])
def test_response_rejects_nonfinite_average_without_retry(average: float) -> None:
    with pytest.raises(ValueError, match="average"):
        fetch_payload(
            {"group_id": 1, "count": 1, "average": average, "best_student": None}
        )


@pytest.mark.parametrize("best_student", ["Олена Коваль", 7, True, [], {}])
def test_response_rejects_non_student_best_student_without_retry(
    best_student: object,
) -> None:
    with pytest.raises((TypeError, ValueError), match="best_student"):
        fetch_payload(
            {"group_id": 1, "count": 1, "average": 90, "best_student": best_student}
        )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("student_id", True),
        ("student_id", 0),
        ("student_id", "7"),
        ("group_id", False),
        ("group_id", -1),
        ("group_id", 1.0),
        ("first_name", 123),
        ("first_name", "   "),
        ("last_name", None),
        ("last_name", ""),
        ("group", []),
        ("group", "\t"),
        ("average_grade", True),
        ("average_grade", "94.5"),
        ("average_grade", -1),
        ("average_grade", 101),
        ("average_grade", float("nan")),
        ("average_grade", float("inf")),
        ("average_grade", -float("inf")),
        ("email", 123),
        ("unexpected", "extra"),
    ],
)
def test_response_rejects_invalid_best_student_field_without_retry(
    field: str, value: object
) -> None:
    student = {**student_payload(), field: value}
    with pytest.raises((TypeError, ValueError), match="best_student"):
        fetch_payload(
            {"group_id": 1, "count": 1, "average": 90, "best_student": student}
        )


@pytest.mark.parametrize(
    "field",
    ["student_id", "first_name", "last_name", "group_id", "group", "average_grade"],
)
def test_response_rejects_missing_best_student_field_without_retry(field: str) -> None:
    student = student_payload()
    del student[field]
    with pytest.raises(ValueError, match="best_student"):
        fetch_payload(
            {"group_id": 1, "count": 1, "average": 90, "best_student": student}
        )


@pytest.mark.parametrize("grade", [0, 100, 94.5])
@pytest.mark.parametrize("email", [None, "olena@example.com"])
def test_response_preserves_student_response(grade: float, email: str | None) -> None:
    student = {**student_payload(), "average_grade": grade, "email": email}
    payload: dict[str, object] = {
        "group_id": 1,
        "count": 1,
        "average": 90,
        "best_student": student,
    }
    assert fetch_payload(payload) == [payload]


def test_response_accepts_omitted_optional_student_email() -> None:
    student = student_payload()
    del student["email"]
    payload: dict[str, object] = {
        "group_id": 1,
        "count": 1,
        "average": 90.5,
        "best_student": student,
    }
    assert fetch_payload(payload) == [payload]


class GroupClientTests(unittest.TestCase):
    # тести асинхронного клієнта статистики груп

    def test_validation_rejects_invalid_group_ids(self) -> None:
        # валідація відкидає некоректні ідентифікатори груп
        invalid_cases = [
            [0],
            [-1],
            [-42],
            [True],
            [False],
            [1, 2, "3"],
            [1, 2.5],
            [1, None],
        ]
        for bad_ids in invalid_cases:
            with (
                self.subTest(bad_ids=bad_ids),
                self.assertRaises((TypeError, ValueError)),
            ):
                asyncio.run(
                    fetch_group_statistics(
                        bad_ids,  # type: ignore[arg-type]
                        base_url="http://testserver",
                    )
                )

    def test_validation_rejects_invalid_options_and_base_url(self) -> None:
        # валідація відкидає некоректні опції та url
        with self.assertRaises((TypeError, ValueError)):
            asyncio.run(
                fetch_group_statistics("invalid", base_url="http://testserver")  # type: ignore[arg-type]
            )
        with self.assertRaises(ValueError):
            asyncio.run(fetch_group_statistics([1], base_url="not-a-valid-url"))
        with self.assertRaises(ValueError):
            asyncio.run(fetch_group_statistics([1], base_url="ftp://testserver"))
        with self.assertRaises(ValueError):
            asyncio.run(fetch_group_statistics([1], base_url="   "))
        with self.assertRaises(TypeError):
            asyncio.run(
                fetch_group_statistics([1], base_url=123)  # type: ignore[arg-type]
            )
        with self.assertRaises(ValueError):
            asyncio.run(
                fetch_group_statistics([1], base_url="http://testserver", timeout=-1.0)
            )
        with self.assertRaises(TypeError):
            asyncio.run(
                fetch_group_statistics(
                    [1],
                    base_url="http://testserver",
                    timeout="bad",  # type: ignore[arg-type]
                )
            )
        with self.assertRaises(ValueError):
            asyncio.run(
                fetch_group_statistics([1], base_url="http://testserver", retries=-1)
            )
        with self.assertRaises(TypeError):
            asyncio.run(
                fetch_group_statistics(
                    [1],
                    base_url="http://testserver",
                    retries=1.5,  # type: ignore[arg-type]
                )
            )
        with self.assertRaises(ValueError):
            asyncio.run(
                fetch_group_statistics([1], base_url="http://testserver", concurrency=0)
            )
        with self.assertRaises(TypeError):
            asyncio.run(
                fetch_group_statistics(
                    [1],
                    base_url="http://testserver",
                    concurrency="2",  # type: ignore[arg-type]
                )
            )
        with self.assertRaises(ValueError):
            asyncio.run(
                fetch_group_statistics([1], base_url="http://testserver", backoff=-0.1)
            )
        with self.assertRaises(TypeError):
            asyncio.run(
                fetch_group_statistics(
                    [1],
                    base_url="http://testserver",
                    backoff="zero",  # type: ignore[arg-type]
                )
            )
        with self.assertRaises(TypeError):
            asyncio.run(
                fetch_group_statistics(
                    [1],
                    base_url="http://testserver",
                    client=object(),  # type: ignore[arg-type]
                )
            )

    def test_empty_group_ids_returns_empty_list(self) -> None:
        # порожній список груп повертає порожній результат
        res = asyncio.run(fetch_group_statistics([], base_url="http://testserver"))
        self.assertEqual(res, [])

    def test_timeout_retry_then_success(self) -> None:
        # таймаут на першому запиті повторюється і повертає 200
        call_count = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise httpx.ReadTimeout("connection timed out", request=request)
            return httpx.Response(
                200,
                json={
                    "group_id": 1,
                    "count": 25,
                    "average": 89.4,
                    "best_student": student_payload(),
                },
            )

        transport = httpx.MockTransport(handler)

        async def run_client() -> list[dict[str, object]]:
            async with httpx.AsyncClient(transport=transport) as client:
                return await fetch_group_statistics(
                    [1],
                    base_url="http://testserver",
                    client=client,
                    retries=2,
                    backoff=0.01,
                )

        results = asyncio.run(run_client())
        self.assertEqual(call_count, 2)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["group_id"], 1)
        self.assertEqual(results[0]["count"], 25)

    def test_server_error_500_retry_then_success(self) -> None:
        # помилка 500 повторюється і повертає 200
        call_count = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return httpx.Response(500, text="Internal Server Error")
            return httpx.Response(
                200,
                json={
                    "group_id": 2,
                    "count": 0,
                    "average": None,
                    "best_student": None,
                },
            )

        transport = httpx.MockTransport(handler)

        async def run_client() -> list[dict[str, object]]:
            async with httpx.AsyncClient(transport=transport) as client:
                return await fetch_group_statistics(
                    [2],
                    base_url="http://testserver",
                    client=client,
                    retries=2,
                    backoff=0.01,
                )

        results = asyncio.run(run_client())
        self.assertEqual(call_count, 2)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["group_id"], 2)
        self.assertEqual(results[0]["count"], 0)
        self.assertIsNone(results[0]["average"])

    def test_permanent_404_raises_immediately_without_retry(self) -> None:
        # помилка 404 викидається одразу без повторних спроб
        call_count = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal call_count
            call_count += 1
            return httpx.Response(404, json={"detail": "Group not found"})

        transport = httpx.MockTransport(handler)

        async def run_client() -> None:
            async with httpx.AsyncClient(transport=transport) as client:
                await fetch_group_statistics(
                    [99],
                    base_url="http://testserver",
                    client=client,
                    retries=3,
                    backoff=0.01,
                )

        with self.assertRaises(httpx.HTTPStatusError) as ctx:
            asyncio.run(run_client())
        self.assertEqual(ctx.exception.response.status_code, 404)
        self.assertEqual(call_count, 1)

    def test_malformed_json_schema_fails_immediately_no_retry(self) -> None:
        # некоректна схема відповіді падає без повторних спроб
        call_count = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal call_count
            call_count += 1
            # пропущене поле average і невірний тип count
            return httpx.Response(
                200,
                json={"group_id": 1, "count": "not-an-int"},
            )

        transport = httpx.MockTransport(handler)

        async def run_client() -> None:
            async with httpx.AsyncClient(transport=transport) as client:
                await fetch_group_statistics(
                    [1],
                    base_url="http://testserver",
                    client=client,
                    retries=3,
                    backoff=0.01,
                )

        with self.assertRaises((TypeError, ValueError)):
            asyncio.run(run_client())
        self.assertEqual(call_count, 1)

    def test_concurrency_tracked_peak_le_limit(self) -> None:
        # пікове число паралельних мережевих запитів не перевищує ліміт
        concurrency_limit = 2
        current_active = 0
        peak_active = 0
        lock = asyncio.Lock()

        async def handler(request: httpx.Request) -> httpx.Response:
            nonlocal current_active, peak_active
            async with lock:
                current_active += 1
                peak_active = max(peak_active, current_active)
            await asyncio.sleep(0.03)
            async with lock:
                current_active -= 1
            gid = int(str(request.url).split("/")[-2])
            return httpx.Response(
                200,
                json={
                    "group_id": gid,
                    "count": gid * 10,
                    "average": 80.0,
                    "best_student": None,
                },
            )

        transport = httpx.MockTransport(handler)

        async def run_client() -> list[dict[str, object]]:
            async with httpx.AsyncClient(transport=transport) as client:
                return await fetch_group_statistics(
                    list(range(1, 7)),
                    base_url="http://testserver",
                    client=client,
                    concurrency=concurrency_limit,
                    retries=0,
                )

        results = asyncio.run(run_client())
        self.assertEqual(len(results), 6)
        self.assertLessEqual(peak_active, concurrency_limit)
        self.assertGreaterEqual(peak_active, 2)

    def test_ordered_results_preserved_despite_different_latencies(self) -> None:
        # порядок результатів збігається з порядком вхідних group_id
        async def handler(request: httpx.Request) -> httpx.Response:
            gid = int(str(request.url).split("/")[-2])
            # робимо затримку для першої групи більшою
            if gid == 3:
                await asyncio.sleep(0.05)
            elif gid == 1:
                await asyncio.sleep(0.01)
            else:
                await asyncio.sleep(0.02)
            return httpx.Response(
                200,
                json={
                    "group_id": gid,
                    "count": 10 + gid,
                    "average": 75.0 + gid,
                    "best_student": student_payload(gid),
                },
            )

        transport = httpx.MockTransport(handler)

        async def run_client() -> list[dict[str, object]]:
            async with httpx.AsyncClient(transport=transport) as client:
                return await fetch_group_statistics(
                    [3, 1, 2],
                    base_url="http://testserver",
                    client=client,
                    concurrency=3,
                )

        results = asyncio.run(run_client())
        result_ids = [res["group_id"] for res in results]
        self.assertEqual(result_ids, [3, 1, 2])

    def test_owned_client_closure_and_external_client_remains_open(self) -> None:
        # власний клієнт закривається, а переданий ззовні залишається відкритим
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "group_id": 1,
                    "count": 5,
                    "average": 90.0,
                    "best_student": None,
                },
            )

        transport = httpx.MockTransport(handler)

        # 1. зовнішній клієнт залишається відкритим
        async def run_external() -> None:
            ext_client = httpx.AsyncClient(transport=transport)
            try:
                res = await fetch_group_statistics(
                    [1],
                    base_url="http://testserver",
                    client=ext_client,
                )
                self.assertEqual(len(res), 1)
                self.assertFalse(ext_client.is_closed)
            finally:
                await ext_client.aclose()

        asyncio.run(run_external())

        # 2. створений всередині клієнт коректно закривається
        captured_client = httpx.AsyncClient(transport=transport)

        with patch(
            "student_manager.group_client.httpx.AsyncClient",
            return_value=captured_client,
        ):
            res = asyncio.run(fetch_group_statistics([1], base_url="http://testserver"))
            self.assertEqual(len(res), 1)
            self.assertTrue(captured_client.is_closed)

    def test_cancellation_cancels_pending_tasks(self) -> None:
        # скасування запиту коректно скасовує активні задачі
        cancelled_count = 0

        async def handler(request: httpx.Request) -> httpx.Response:
            nonlocal cancelled_count
            try:
                await asyncio.sleep(0.5)
            except asyncio.CancelledError:
                cancelled_count += 1
                raise
            return httpx.Response(
                200,
                json={"group_id": 1, "count": 1, "average": 90.0, "best_student": None},
            )

        transport = httpx.MockTransport(handler)

        async def run_and_cancel() -> None:
            async with httpx.AsyncClient(transport=transport) as client:
                task = asyncio.create_task(
                    fetch_group_statistics(
                        [1, 2],
                        base_url="http://testserver",
                        client=client,
                        concurrency=2,
                    )
                )
                await asyncio.sleep(0.02)
                task.cancel()
                with self.assertRaises(asyncio.CancelledError):
                    await task

        asyncio.run(run_and_cancel())
        self.assertGreaterEqual(cancelled_count, 1)

    def test_rate_limit_429_retry_then_success(self) -> None:
        # статус 429 повторюється і повертає успіх
        call_count = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return httpx.Response(429, text="Too Many Requests")
            return httpx.Response(
                200,
                json={
                    "group_id": 5,
                    "count": 12,
                    "average": 82.5,
                    "best_student": student_payload(5),
                },
            )

        transport = httpx.MockTransport(handler)

        async def run_client() -> list[dict[str, object]]:
            async with httpx.AsyncClient(transport=transport) as client:
                return await fetch_group_statistics(
                    [5],
                    base_url="http://testserver",
                    client=client,
                    retries=2,
                    backoff=0.01,
                )

        results = asyncio.run(run_client())
        self.assertEqual(call_count, 2)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["group_id"], 5)

    def test_retries_exhaustion_raises_http_error(self) -> None:
        # вичерпання спроб при 503 викидає HTTPStatusError
        call_count = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal call_count
            call_count += 1
            return httpx.Response(503, text="Service Unavailable")

        transport = httpx.MockTransport(handler)

        async def run_client() -> None:
            async with httpx.AsyncClient(transport=transport) as client:
                await fetch_group_statistics(
                    [1],
                    base_url="http://testserver",
                    client=client,
                    retries=2,
                    backoff=0.01,
                )

        with self.assertRaises(httpx.HTTPStatusError):
            asyncio.run(run_client())
        self.assertEqual(call_count, 3)

    def test_timeout_retries_exhaustion_raises_timeout_error(self) -> None:
        # вичерпання спроб при таймауті викидає ReadTimeout
        call_count = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal call_count
            call_count += 1
            raise httpx.ReadTimeout("read timed out", request=request)

        transport = httpx.MockTransport(handler)

        async def run_client() -> None:
            async with httpx.AsyncClient(transport=transport) as client:
                await fetch_group_statistics(
                    [1],
                    base_url="http://testserver",
                    client=client,
                    retries=1,
                    backoff=0.01,
                )

        with self.assertRaises(httpx.ReadTimeout):
            asyncio.run(run_client())
        self.assertEqual(call_count, 2)

    def test_malformed_raw_json_raises_value_error(self) -> None:
        # невалідний синтаксис json кидає ValueError
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, text="not valid json {[}")

        transport = httpx.MockTransport(handler)

        async def run_client() -> None:
            async with httpx.AsyncClient(transport=transport) as client:
                await fetch_group_statistics(
                    [1],
                    base_url="http://testserver",
                    client=client,
                )

        with self.assertRaises(ValueError):
            asyncio.run(run_client())

    def test_schema_validation_rejects_various_invalid_structures(self) -> None:
        # перевірка різних порушень схеми відповіді
        cases = [
            [1, 2, 3],  # not dict
            {"group_id": 1, "count": 2},  # missing keys
            {
                "group_id": 999,
                "count": 2,
                "average": 80.0,
                "best_student": None,
            },  # wrong group_id
            {
                "group_id": 1,
                "count": -5,
                "average": 80.0,
                "best_student": None,
            },  # count < 0
            {
                "group_id": 1,
                "count": 2,
                "average": "eighty",
                "best_student": None,
            },  # average not number
        ]
        for bad_payload in cases:
            transport = httpx.MockTransport(
                lambda req, p=bad_payload: httpx.Response(200, json=p)
            )

            async def run_client(tr: httpx.MockTransport) -> None:
                async with httpx.AsyncClient(transport=tr) as client:
                    await fetch_group_statistics(
                        [1],
                        base_url="http://testserver",
                        client=client,
                        retries=0,
                    )

            with (
                self.subTest(bad_payload=bad_payload),
                self.assertRaises((TypeError, ValueError)),
            ):
                asyncio.run(run_client(transport))
