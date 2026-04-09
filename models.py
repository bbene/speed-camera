"""
SQLAlchemy ORM models for speed camera detections
"""
from sqlalchemy import Column, Integer, Float, String, DateTime, LargeBinary, Index
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime

Base = declarative_base()


class Detection(Base):
    """
    ORM model for a single vehicle detection event
    """
    __tablename__ = 'detections'

    id = Column(Integer, primary_key=True)
    timestamp = Column(DateTime, nullable=False, index=True)
    speed_mph = Column(Float, nullable=False)
    speed_deviation = Column(Float)
    area = Column(Integer)
    area_deviation = Column(Float)
    frames = Column(Integer)
    seconds = Column(Float)
    direction = Column(String(3))  # 'LTR' or 'RTL'
    confidence = Column(Float)
    gif_data = Column(LargeBinary)  # GIF stored as BLOB
    created_at = Column(DateTime, default=datetime.utcnow, index=True)

    # Create compound index for common queries
    __table_args__ = (
        Index('idx_timestamp_direction_speed', 'timestamp', 'direction', 'speed_mph'),
    )

    def __repr__(self):
        return (
            f"<Detection(id={self.id}, timestamp={self.timestamp}, "
            f"speed_mph={self.speed_mph}, direction={self.direction})>"
        )

    def to_dict(self):
        """Convert detection to dictionary for JSON serialization"""
        return {
            'id': self.id,
            'timestamp': self.timestamp.isoformat() if self.timestamp else None,
            'speed_mph': round(self.speed_mph, 1),
            'speed_deviation': round(self.speed_deviation, 1) if self.speed_deviation else None,
            'area': self.area,
            'area_deviation': round(self.area_deviation, 1) if self.area_deviation else None,
            'frames': self.frames,
            'seconds': round(self.seconds, 2) if self.seconds else None,
            'direction': self.direction,
            'confidence': round(self.confidence, 1) if self.confidence else None,
            'has_gif': self.gif_data is not None
        }
