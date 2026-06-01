from datetime import datetime
from sqlalchemy import Column, Integer, String, Boolean, DateTime, JSON
from app.db.base_class import Base

class Node(Base):
    __tablename__ = "nodes"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False, unique=True)
    address = Column(String, nullable=False) # IP или домен ноды
    api_port = Column(Integer, default=8080)
    
    # Протоколы, которые поддерживает нода (xray, hysteria2)
    supported_protocols = Column(JSON, default=list)
    
    is_active = Column(Boolean, default=True)
    
    # Сертификаты для защищенного общения с нодой (опционально)
    cert_path = Column(String, nullable=True)
    key_path = Column(String, nullable=True)
    
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    last_seen = Column(DateTime(timezone=True), nullable=True)
