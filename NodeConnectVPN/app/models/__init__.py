from app.db.base_class import Base
from app.models.user import User
from app.models.node import Node
from app.models.subscription import Subscription

# Этот файл нужен, чтобы Alembic "видел" все модели при автогенерации миграций
