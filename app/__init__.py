"""Flask application factory (MVC + CQRS skeleton)."""

from flask import Flask
from sqlalchemy import create_engine

from app.config import Config
from app.db import Base, close_session


def create_app():
    flask_app = Flask(
        __name__,
        template_folder="views",
        static_folder="static",
    )
    flask_app.config.from_object(Config)

    flask_app.engine = create_engine(
        flask_app.config["DATABASE_URL"],
        pool_pre_ping=True,
    )

    # Register models on metadata, then create missing tables.
    from app.models import event as _event_model  # noqa: F401
    from app.models import listing as _listing_model  # noqa: F401
    from app.models import user as _user_model  # noqa: F401

    Base.metadata.create_all(bind=flask_app.engine)

    from app.controllers.auth import auth_bp
    from app.controllers.home import home_bp
    from app.controllers.listings import listings_bp

    flask_app.register_blueprint(home_bp)
    flask_app.register_blueprint(auth_bp)
    flask_app.register_blueprint(listings_bp)
    flask_app.teardown_appcontext(close_session)

    return flask_app