"""Integration tests for real temporary SQLite databases and ownership boundaries."""

from pathlib import Path

import pytest

from backend.services.user_database import RuntimeDatabaseError, RuntimeDatabaseNotFoundError, UserDatabase


@pytest.fixture(name="runtime_database")
def fixture_runtime_database(tmp_path: Path):
    service = UserDatabase(temp_root=tmp_path)
    yield service
    service.close()


def test_bundled_samples_are_registered_with_the_expected_schema(
    runtime_database: UserDatabase,
) -> None:
    netflix = runtime_database.register_sample_sqlite(user_id=11, sample_name="netflix")
    uber = runtime_database.register_sample_sqlite(user_id=11, sample_name="uber")

    assert netflix.id == "sample-11"
    assert uber.id == "sample-uber-11"
    assert {table.name for table in runtime_database.get_schema(netflix.id, user_id=11)} == {
        "netflix_titles"
    }
    assert (
        runtime_database.count_rows(
            uber.id, user_id=11, table_name="uber_ride_bookings"
        )
        > 0
    )


def test_runtime_database_cannot_be_read_or_removed_by_another_user(
    runtime_database: UserDatabase,
) -> None:
    registered = runtime_database.register_sample_sqlite(user_id=11)

    with pytest.raises(RuntimeDatabaseNotFoundError):
        runtime_database.get_schema(registered.id, user_id=22)
    with pytest.raises(RuntimeDatabaseNotFoundError):
        runtime_database.remove_database(registered.id, user_id=22)

    assert runtime_database.get_database(registered.id, user_id=11).id == registered.id


def test_uploaded_database_is_validated_and_its_temporary_file_is_removed(
    runtime_database: UserDatabase,
) -> None:
    content = (Path("frontend/test_data/laptops.db")).read_bytes()
    registered = runtime_database.register_uploaded_sqlite(
        user_id=11,
        display_name="Inventario de laptops",
        filename="laptops.db",
        content=content,
        runtime_id="laptops-test",
    )
    path = runtime_database.get_database(registered.id, user_id=11).path

    assert path.exists()
    assert runtime_database.get_schema(registered.id, user_id=11)
    runtime_database.remove_database(registered.id, user_id=11)
    assert not path.exists()


@pytest.mark.parametrize("filename,content", [("notes.txt", b"SQLite format 3\\x00"), ("empty.db", b"")])
def test_upload_rejects_unsafe_or_empty_files(
    runtime_database: UserDatabase, filename: str, content: bytes
) -> None:
    with pytest.raises(RuntimeDatabaseError):
        runtime_database.register_uploaded_sqlite(
            user_id=11,
            display_name="Invalid",
            filename=filename,
            content=content,
        )
