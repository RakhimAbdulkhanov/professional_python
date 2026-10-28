import importlib
import importlib.util
import unittest


class BenchmarkTests(unittest.TestCase):
    def test_invalid_measurement_parameters_are_rejected(self):
        module = importlib.import_module("student_manager.experiments")
        for sizes, repeats in [((0,), 1), ((-1,), 1), ((10,), 0)]:
            with (
                self.subTest(sizes=sizes, repeats=repeats),
                self.assertRaises(ValueError),
            ):
                module.lookup_benchmark(sizes, repeats=repeats)

    def test_lookup_measurements_use_equal_results(self):
        self.assertIsNotNone(importlib.util.find_spec("student_manager.experiments"))
        module = importlib.import_module("student_manager.experiments")
        rows = module.lookup_benchmark((10, 100), repeats=3)
        self.assertEqual([row["records"] for row in rows], [10, 100])
        for row in rows:
            self.assertGreaterEqual(row["list_seconds"], 0)
            self.assertGreaterEqual(row["dict_seconds"], 0)
            self.assertGreaterEqual(row["build_seconds"], 0)


if __name__ == "__main__":
    unittest.main()
