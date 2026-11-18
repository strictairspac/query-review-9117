import jwt
from fastapi import Depends,HTTPException
from fastapi.security import HTTPBearer
from sqlalchemy import select
from ..config.database import get_db
from ..config.settings import JWT_SECRET
from ..models.user import User
bearer=HTTPBearer()
def current_user(token=Depends(bearer),db=Depends(get_db)):
    try:
        payload=jwt.decode(token.credentials,JWT_SECRET,algorithms=['HS256'])
        user=db.scalar(select(User).where(User.email==payload['sub']))
        if not user: raise ValueError()
        return user
    except Exception: raise HTTPException(401,'登录已过期，请重新登录')
def writer(user=Depends(current_user)):
    if user.role not in ('admin','operator'): raise HTTPException(403,'观察员只能查看与导出')
    return user
def admin(user=Depends(current_user)):
    if user.role!='admin': raise HTTPException(403,'仅管理员可查看审计')
    return user
