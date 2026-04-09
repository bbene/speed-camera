"""
Database initialization and connection management
"""
import os
import logging
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, Session
from models import Base, Detection

logger = logging.getLogger(__name__)


class Database:
    """Database connection and session management"""

    def __init__(self, database_url=None):
        """
        Initialize database connection

        Args:
            database_url: PostgreSQL connection string
                         If None, reads from DATABASE_URL environment variable
        """
        if database_url is None:
            database_url = os.environ.get(
                'DATABASE_URL',
                'postgresql://speed_camera:password@postgres:5432/speed_camera'
            )

        self.database_url = database_url
        self.engine = create_engine(
            database_url,
            echo=False,
            pool_pre_ping=True,  # Test connections before using
            pool_size=10,
            max_overflow=20
        )

        # Enable connection pooling
        @event.listens_for(self.engine, "connect")
        def receive_connect(dbapi_conn, connection_record):
            """Configure connection on connect"""
            pass

        self.SessionLocal = sessionmaker(
            autocommit=False,
            autoflush=False,
            bind=self.engine
        )

    def init_db(self):
        """Create all tables"""
        try:
            Base.metadata.create_all(bind=self.engine)
            logger.info("Database tables created successfully")
        except Exception as e:
            logger.error(f"Failed to create database tables: {e}")
            raise

    def get_session(self) -> Session:
        """Get a new database session"""
        return self.SessionLocal()

    def add_detection(self, detection: Detection) -> Detection:
        """
        Add a detection record to the database

        Args:
            detection: Detection ORM object

        Returns:
            The saved Detection object with ID
        """
        session = self.get_session()
        try:
            session.add(detection)
            session.commit()
            session.refresh(detection)
            logger.debug(f"Detection recorded: {detection.id} - {detection.speed_mph} mph")
            return detection
        except Exception as e:
            session.rollback()
            logger.error(f"Failed to record detection: {e}")
            raise
        finally:
            session.close()

    def close(self):
        """Close database connection pool"""
        self.engine.dispose()


# Global database instance
_db = None


def init_database(database_url=None) -> Database:
    """Initialize and return database instance"""
    global _db
    _db = Database(database_url)
    _db.init_db()
    return _db


def get_database() -> Database:
    """Get global database instance"""
    global _db
    if _db is None:
        _db = Database()
        _db.init_db()
    return _db
