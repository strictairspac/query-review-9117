from datetime import datetime,timedelta,timezone
import jwt
from fastapi import HTTPException
from sqlalchemy import select
from ..models.user import User
from ..config.settings import JWT_SECRET
from ..utils.password import verify
def login(db,email,password):
    user=db.scalar(select(User).where(User.email==email))
    if not user or not verify(password,user.password_hash):raise HTTPException(401,'账号或密码不正确')
    return {'token':jwt.encode({'sub':user.email,'exp':datetime.now(timezone.utc)+timedelta(hours=8)},JWT_SECRET,algorithm='HS256'),'email':user.email,'role':user.role}
