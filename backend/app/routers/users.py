"""User management — admin only."""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, EmailStr

from app import db
from app.auth import AdminUser, AnyUser, ALL_PERMISSIONS

router = APIRouter()


class CreateUserRequest(BaseModel):
    name: str
    email: EmailStr
    password: str
    is_admin: bool = False
    permissions: list[str] = []


class UpdateUserRequest(BaseModel):
    name: str | None = None
    is_active: bool | None = None
    permissions: list[str] | None = None
    password: str | None = None


class UserResponse(BaseModel):
    id: int
    name: str
    email: str
    is_admin: bool
    is_active: bool
    permissions: list[str]
    created_at: str
    updated_at: str


@router.get("/permissions/all", summary="List all available permissions")
def list_all_permissions(_: AnyUser):
    return {"permissions": ALL_PERMISSIONS}


@router.get("/me", response_model=UserResponse)
def get_me(user: AnyUser):
    row = db.user_get_by_id(user.user_id)
    if not row:
        raise HTTPException(404, "User not found")
    return UserResponse(**{k: row[k] for k in UserResponse.model_fields})


@router.get("/", response_model=list[UserResponse])
def list_users(_: AdminUser):
    users = db.user_list()
    return [UserResponse(**{k: u[k] for k in UserResponse.model_fields}) for u in users]


@router.post("/", response_model=UserResponse, status_code=201)
def create_user(body: CreateUserRequest, _: AdminUser):
    # Validate permissions
    bad = [p for p in body.permissions if p not in ALL_PERMISSIONS]
    if bad:
        raise HTTPException(400, f"Unknown permissions: {bad}")

    try:
        user = db.user_create(
            name=body.name,
            email=body.email,
            password=body.password,
            is_admin=body.is_admin,
            permissions=body.permissions,
        )
    except Exception as e:
        if "UNIQUE" in str(e):
            raise HTTPException(409, f"A user with email {body.email} already exists")
        raise

    return UserResponse(**{k: user[k] for k in UserResponse.model_fields})


@router.patch("/{user_id}", response_model=UserResponse)
def update_user(user_id: int, body: UpdateUserRequest, _: AdminUser):
    if body.permissions is not None:
        bad = [p for p in body.permissions if p not in ALL_PERMISSIONS]
        if bad:
            raise HTTPException(400, f"Unknown permissions: {bad}")

    user = db.user_update(
        user_id,
        name=body.name,
        is_active=body.is_active,
        permissions=body.permissions,
        password=body.password,
    )
    if not user:
        raise HTTPException(404, "User not found")
    return UserResponse(**{k: user[k] for k in UserResponse.model_fields})


@router.delete("/{user_id}", status_code=204)
def delete_user(user_id: int, current: AdminUser):
    if user_id == current.user_id:
        raise HTTPException(400, "Cannot delete your own account")
    db.user_delete(user_id)
