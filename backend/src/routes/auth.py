from fastapi import APIRouter,Depends
from pydantic import BaseModel,Field
from ..config.database import get_db
from ..controllers.auth import login
from ..services.auth import current_user
router=APIRouter(prefix='/auth')
class Login(BaseModel):
    email:str=Field(max_length=120)
    password:str=Field(max_length=100)
@router.post('/login')
def signin(data:Login,db=Depends(get_db)):return login(db,data.email,data.password)
@router.get('/me')
def me(user=Depends(current_user)):return {'email':user.email,'role':user.role}
