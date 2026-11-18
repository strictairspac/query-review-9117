import json
from fastapi import APIRouter,Depends,Response
from ..config.database import get_db
from ..schemas.evidence import EvidenceOutput
from ..services.auth import current_user
from ..services.evidence import list_evidence,get_evidence
router=APIRouter(prefix='/evidence')
@router.get('',response_model=list[EvidenceOutput])
def listing(db=Depends(get_db),user=Depends(current_user)):return list_evidence(db)
@router.get('/{batch_id}',response_model=EvidenceOutput)
def detail(batch_id:int,db=Depends(get_db),user=Depends(current_user)):return get_evidence(db,batch_id)
@router.get('/{batch_id}/export')
def export(batch_id:int,db=Depends(get_db),user=Depends(current_user)):
    result=get_evidence(db,batch_id)
    return Response(json.dumps(result,ensure_ascii=False,indent=2),media_type='application/json',headers={'Content-Disposition':f'attachment; filename="review-{batch_id}.json"'})
