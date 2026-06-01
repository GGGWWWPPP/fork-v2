import uuid
from datetime import datetime
from sqlalchemy import Column, Integer, BigInteger, String, Boolean, DateTime, Enum as SQLEnum
from app.db.base_class import Base
from sqlalchemy.orm import relationship
import enum

class UserStatus(str, enum.Enum):
    ACTIVE = "active"
    DISABLED = "disabled"
    EXPIRED = "expired"

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    uuid = Column(String, unique=True, index=True, default=lambda: str(uuid.uuid4()))
    username = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    
    status = Column(SQLEnum(UserStatus), default=UserStatus.ACTIVE)
    is_admin = Column(Boolean, default=False)
    
    data_limit_bytes = Column(BigInteger, default=0) # 0 = безлимит
    used_traffic_bytes = Column(BigInteger, default=0)
    expire_date = Column(DateTime(timezone=True), nullable=True)
    
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    
    # Отношения (будут загружаться лениво или через joinedload)
    subscriptions = relationship("Subscription", back_populates="user", cascade="all, delete-orphan")
