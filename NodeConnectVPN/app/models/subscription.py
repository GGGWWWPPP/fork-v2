import uuid
from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Boolean
from app.db.base_class import Base
from sqlalchemy.orm import relationship

class Subscription(Base):
    __tablename__ = "subscriptions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    
    # Уникальный токен подписки (для ссылки)
    token = Column(String, unique=True, index=True, default=lambda: str(uuid.uuid4()))
    
    # Fingerprinting (защита от копирования)
    fingerprint = Column(String, nullable=True) # Хэш IP + User-Agent или сгенерированный client_id
    last_ip = Column(String, nullable=True)
    
    is_revoked = Column(Boolean, default=False)
    
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    last_used = Column(DateTime(timezone=True), nullable=True)

    # Отношения
    user = relationship("User", back_populates="subscriptions")
