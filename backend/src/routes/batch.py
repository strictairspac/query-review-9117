from fastapi import APIRouter,Depends
from ..config.database import get_db
from ..schemas.batch import BatchInput
from ..services.auth import current_user,writer
from ..services.batch import list_batches,create_batch
router=APIRouter(prefix='/batches')
@router.get('')
def listing(db=Depends(get_db),user=Depends(current_user)):return list_batches(db)
@router.post('',status_code=202)
def create(data:BatchInput,db=Depends(get_db),user=Depends(writer)):return create_batch(db,data)
