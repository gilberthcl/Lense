"""Local access-PIN endpoints. These are exempt from the auth middleware."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.services import auth

router = APIRouter(prefix="/api/auth", tags=["auth"])

PIN_LEN = 6


class PinBody(BaseModel):
    pin: str

    @field_validator("pin")
    @classmethod
    def _len(cls, v: str) -> str:
        if len(v) != PIN_LEN:
            raise ValueError(f"PIN must be exactly {PIN_LEN} characters")
        return v


class ChangeBody(BaseModel):
    current_pin: str
    new_pin: str

    @field_validator("new_pin")
    @classmethod
    def _len(cls, v: str) -> str:
        if len(v) != PIN_LEN:
            raise ValueError(f"PIN must be exactly {PIN_LEN} characters")
        return v


@router.get("/status")
def status():
    return {"configured": auth.configured()}


@router.post("/setup")
def setup(body: PinBody, db: Session = Depends(get_db)):
    if auth.configured():
        raise HTTPException(status_code=409, detail="A PIN is already set")
    return {"token": auth.setup(db, body.pin)}


@router.post("/login")
def login(body: PinBody, db: Session = Depends(get_db)):
    if not auth.configured():
        raise HTTPException(status_code=400, detail="No PIN configured")
    token = auth.verify(db, body.pin)
    if token is None:
        raise HTTPException(status_code=401, detail="Incorrect PIN")
    return {"token": token}


@router.post("/change")
def change(body: ChangeBody, db: Session = Depends(get_db)):
    token = auth.change(db, body.current_pin, body.new_pin)
    if token is None:
        raise HTTPException(status_code=401, detail="Current PIN is incorrect")
    return {"token": token}
