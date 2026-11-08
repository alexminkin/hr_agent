from sqlalchemy import create_engine, inspect

from hr_agent.db import Base


def test_attempt_and_notification_tables_can_be_created():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    names = set(inspect(engine).get_table_names())
    assert {"applications", "job_attempts", "notifications"} <= names
