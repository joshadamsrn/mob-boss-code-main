from pathlib import Path


_SQLITE_TEST_ARTIFACT = Path("file:memorydb_default?mode=memory&cache=shared")


def pytest_sessionfinish(session, exitstatus) -> None:
    if _SQLITE_TEST_ARTIFACT.exists():
        _SQLITE_TEST_ARTIFACT.unlink()
