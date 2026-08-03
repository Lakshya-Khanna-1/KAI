from fastapi import APIRouter

router = APIRouter(prefix="/dummy", tags=["dummy"])


@router.get("/ping")
def ping():
    return {"message": "pong"}
