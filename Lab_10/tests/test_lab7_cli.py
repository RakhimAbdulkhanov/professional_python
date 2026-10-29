import subprocess
import sys


def test_lab7_mode_uses_existing_entrypoint(tmp_path):
    path = tmp_path / "students.sqlite"
    result = subprocess.run(
        [sys.executable, "-m", "student_manager.main", "--lab7", str(path)],
        capture_output=True,
        check=False,
        text=True,
        encoding="utf-8",
    )
    assert result.returncode == 0, result.stderr
    assert path.exists()
    assert "відкат підтверджено" in result.stdout
