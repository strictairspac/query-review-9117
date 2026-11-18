import jwt
from starlette.middleware.base import BaseHTTPMiddleware
from ..config.database import Session
from ..config.settings import JWT_SECRET
from ..models.audit import Audit
class AuditMiddleware(BaseHTTPMiddleware):
    async def dispatch(self,request,call_next):
        response=await call_next(request)
        if request.method in ('POST','PUT','DELETE'):
            actor='anonymous'
            try:actor=jwt.decode(request.headers.get('Authorization','').split(' ')[1],JWT_SECRET,algorithms=['HS256'])['sub']
            except Exception:pass
            with Session() as db:
                db.add(Audit(actor=actor,action=f'{request.method} {request.url.path} → {response.status_code}'));db.commit()
        return response
