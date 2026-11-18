from fastapi import APIRouter,Depends
from sqlalchemy import select
from ..config.database import get_db
from ..models.audit import Audit
from ..services.auth import admin
router=APIRouter()
@router.get('/audit')
def audit(db=Depends(get_db),user=Depends(admin)):
    return [{'id':x.id,'actor':x.actor,'action':x.action,'created_at':str(x.created_at)} for x in db.scalars(select(Audit).order_by(Audit.id.desc()).limit(100))]
