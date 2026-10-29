import tempfile
import unittest
from pathlib import Path

from student_manager.streaming_experiments import (
    measure_eager_pipeline,
    measure_lazy_pipeline,
)


class ExperimentParityTests(unittest.TestCase):
    def test_eager_lazy_share_validation_including_bad_rows(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "students.csv"
            path.write_text(
                "student_id,first_name,last_name,group,average_grade\n"
                "1,Anna,Koval,A,90\n2,Oleh,Bondar,A,wrong\n3,Ira,Koval,A,95\n",
                encoding="utf-8",
            )
            eager = measure_eager_pipeline(path, "A", 0)
            lazy = measure_lazy_pipeline(path, "A", 0)
            self.assertEqual(eager["stats"], lazy["stats"])
            self.assertEqual(eager["stats"]["count"], 2)
