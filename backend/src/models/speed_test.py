from sqlalchemy.orm import Mapped,mapped_column
from sqlalchemy import String,Integer,ForeignKey,JSON,DateTime,func
from datetime import datetime
from ..config.database import Base
class SpeedTest(Base):
    __tablename__='speed_tests'
    id:Mapped[int]=mapped_column(primary_key=True)
    batch_id:Mapped[int]=mapped_column(ForeignKey('batches.id'))
    status:Mapped[str]=mapped_column(String(20),default='pending')
    rounds:Mapped[list]=mapped_column(JSON,default=list)
    result:Mapped[dict]=mapped_column(JSON,default=dict)
    elapsed_ms:Mapped[int]=mapped_column(Integer,default=0)
    created_at:Mapped[datetime]=mapped_column(DateTime,server_default=func.now())
    finished_at:Mapped[datetime]=mapped_column(DateTime,nullable=True)
