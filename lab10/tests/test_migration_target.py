from student_manager.lab7_demo import apply_migrations


def test_explicit_demo_path_is_not_overridden_by_database_environment(
    tmp_path, monkeypatch
):
    requested = tmp_path / "requested.sqlite"
    unrelated = tmp_path / "unrelated.sqlite"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{unrelated.as_posix()}")
    apply_migrations(requested)
    assert requested.exists()
    assert not unrelated.exists()
