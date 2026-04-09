import time

from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from app.db.base import Base
from app.db.session import engine
from app.models.change_request import ChangeRequest
from app.models.event import Event
from app.models.summary import Summary
from app.models.task import Task
from app.models.user import User


def wait_for_database(max_attempts: int = 20, delay_seconds: int = 3) -> None:
    for attempt in range(1, max_attempts + 1):
        try:
            with engine.connect() as connection:
                connection.execute(text("SELECT 1"))
            print(f"[init-db] Database is ready on attempt {attempt}.", flush=True)
            return
        except OperationalError as exc:
            if attempt == max_attempts:
                raise
            print(
                f"[init-db] Database is not ready on attempt {attempt}/{max_attempts}: {exc}",
                flush=True,
            )
            time.sleep(delay_seconds)


def init_db() -> None:
    wait_for_database()
    Base.metadata.create_all(bind=engine)
    print("[init-db] Schema initialization complete.", flush=True)


if __name__ == "__main__":
    init_db()
