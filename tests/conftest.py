"""Test setup: run the app against a throwaway SQLite file, never the cloud DB."""

import os
import tempfile

import pytest

_DB_FILE = os.path.join(tempfile.mkdtemp(), "test.db")
# Set before app.config is imported; load_dotenv does not override existing vars.
os.environ["DATABASE_URL"] = f"sqlite:///{_DB_FILE}"

from werkzeug.security import generate_password_hash  # noqa: E402

from app import create_app  # noqa: E402
from app.db import Base  # noqa: E402
from app.models.user import User  # noqa: E402


@pytest.fixture
def app():
    flask_app = create_app()
    flask_app.config.update(TESTING=True)
    Base.metadata.drop_all(bind=flask_app.engine)
    Base.metadata.create_all(bind=flask_app.engine)
    yield flask_app


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def db(app):
    from sqlalchemy.orm import sessionmaker

    session = sessionmaker(bind=app.engine)()
    yield session
    session.close()


def make_user(db, email, role):
    user = User(
        name=email.split("@")[0],
        email=email,
        password_hash=generate_password_hash("password123"),
        role=role,
    )
    db.add(user)
    db.commit()
    return user


def login(client, email):
    return client.post("/login", data={"email": email, "password": "password123"})


def make_listing(db, seller, title, status, description="תיאור", category="other",
                 price="100", created_at=None, rejection_reason=None):
    """Insert a read-model row directly; statuses past Pending evaluation have no command yet."""
    import uuid
    from datetime import datetime, timezone
    from decimal import Decimal

    from app.models.listing import Listing

    listing = Listing(
        id=str(uuid.uuid4()),
        seller_id=seller.id,
        title=title,
        description=description,
        category=category,
        price=Decimal(price),
        status=status,
        rejection_reason=rejection_reason,
        created_at=created_at or datetime.now(timezone.utc),
    )
    db.add(listing)
    db.commit()
    return listing
