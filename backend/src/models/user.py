from sqlalchemy.orm import Mapped,mapped_column
from sqlalchemy import String
from ..config.database import Base
class User(Base):
    __tablename__='users'
    id:Mapped[int]=mapped_column(primary_key=True)
    email:Mapped[str]=mapped_column(String(120),unique=True)
    password_hash:Mapped[str]=mapped_column(String(200))
    role:Mapped[str]=mapped_column(String(20))
