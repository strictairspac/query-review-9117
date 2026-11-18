from fastapi import APIRouter,Depends
from ..config.database import get_db
from ..schemas.sample import SampleInput
from ..services.auth import current_user,writer
from ..services.sample import list_samples,create_sample
router=APIRouter(prefix='/samples')
@router.get('')
def listing(db=Depends(get_db),user=Depends(current_user)):return list_samples(db)
@router.post('',status_code=201)
def create(data:SampleInput,db=Depends(get_db),user=Depends(writer)):return create_sample(db,data)
