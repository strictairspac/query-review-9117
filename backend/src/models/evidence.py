from sqlalchemy.orm import Mapped,mapped_column
from sqlalchemy import ForeignKey,JSON
from ..config.database import Base
class Evidence(Base):
    __tablename__='evidence'
    id:Mapped[int]=mapped_column(primary_key=True)
    batch_id:Mapped[int]=mapped_column(ForeignKey('batches.id'),unique=True)
    result:Mapped[dict]=mapped_column(JSON)
