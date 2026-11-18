from sqlalchemy.orm import Mapped,mapped_column
from sqlalchemy import String,Text
from ..config.database import Base
class Sample(Base):
    __tablename__='samples'
    id:Mapped[int]=mapped_column(primary_key=True)
    name:Mapped[str]=mapped_column(String(120),unique=True)
    description:Mapped[str]=mapped_column(Text)
    original_sql:Mapped[str]=mapped_column(Text)
