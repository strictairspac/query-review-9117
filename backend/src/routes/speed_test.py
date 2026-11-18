from fastapi import APIRouter,Depends
from ..config.database import get_db
from ..schemas.speed_test import SpeedTestInput
from ..services.auth import current_user,writer
from ..services.speed_test import list_speed_tests,create_speed_test
router=APIRouter(prefix='/speed-tests')
@router.get('')
def listing(batch_id:int|None=None,db=Depends(get_db),user=Depends(current_user)):
    return list_speed_tests(db,batch_id)
@router.post('',status_code=202)
def create(data:SpeedTestInput,db=Depends(get_db),user=Depends(writer)):
    return create_speed_test(db,data)
