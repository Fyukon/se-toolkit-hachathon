from app.db.base import Base
from app.db.session import engine
from app.models.change_request import ChangeRequest
from app.models.event import Event
from app.models.summary import Summary
from app.models.task import Task
from app.models.user import User


def init_db() -> None:
    Base.metadata.create_all(bind=engine)


if __name__ == "__main__":
    init_db()
