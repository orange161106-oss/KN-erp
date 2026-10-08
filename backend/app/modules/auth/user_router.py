from typing import Annotated
from uuid import UUID
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.schemas.auth import CurrentUser
from app.schemas.user import UserCreate, UserResponse, UserUpdate
from app.security.dependencies import get_current_user
from app.services import users

router = APIRouter(prefix="/users", tags=["user-management"])
Database = Annotated[Session, Depends(get_db)]
Actor = Annotated[CurrentUser, Depends(get_current_user)]


@router.get("", response_model=list[UserResponse])
def list_users(session: Database, actor: Actor):
    return users.list_users(session, actor)


@router.post("", response_model=UserResponse, status_code=201)
def create_user(data: UserCreate, session: Database, actor: Actor):
    return users.create_user(session, data, actor)


@router.put("/{user_id}", response_model=UserResponse)
def update_user(user_id: UUID, data: UserUpdate, session: Database, actor: Actor):
    return users.update_user(session, user_id, data, actor)
