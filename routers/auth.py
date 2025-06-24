from fastapi import APIRouter, HTTPException, Body, Depends
from fastapi.security import OAuth2PasswordRequestForm
from ..scheduler import get_crons
from ..schemas import Token, UserRoleUpdateRequest
from ..services import user_service

router = APIRouter()

oauth2_scheme = user_service.oauth2_scheme
get_current_user = user_service.get_current_user
admin_required = user_service.admin_required

@router.post("/auth/register")
async def register(username: str = Body(...), password: str = Body(...), role: str = Body("user")):
    crons = get_crons()
    backend = crons.state_backend
    if await backend.get_user_by_username(username):
        raise HTTPException(status_code=409, detail="Username already exists")
    await backend.create_user(username, password, role)
    return {"status": "success", "message": f"User '{username}' registered"}

@router.post("/auth/login", response_model=Token)
async def login(form_data: OAuth2PasswordRequestForm = Depends()):
    crons = get_crons()
    backend = crons.state_backend
    user = await user_service.authenticate_user(backend, form_data.username, form_data.password)
    if not user:
        raise HTTPException(status_code=401, detail="Incorrect username or password")
    access_token = user_service.create_access_token(
        data={"sub": user["username"], "role": user["role"]}
    )
    return {"access_token": access_token, "token_type": "bearer"}

@router.get("/users", dependencies=[Depends(admin_required)])
async def list_users():
    crons = get_crons()
    users = await crons.state_backend.get_all_users()
    return users

@router.put("/users/{username}/role", dependencies=[Depends(admin_required)])
async def update_user_role(username: str, req: UserRoleUpdateRequest):
    crons = get_crons()
    user = await crons.state_backend.get_user_by_username(username)
    if not user:
        raise HTTPException(status_code=404, detail=f"User '{username}' not found")
    await crons.state_backend.update_user_role(username, req.new_role)
    return {"status": "success", "message": f"User '{username}' role updated to '{req.new_role}'"}

@router.delete("/users/{username}", dependencies=[Depends(admin_required)])
async def delete_user(username: str):
    crons = get_crons()
    user = await crons.state_backend.get_user_by_username(username)
    if not user:
        raise HTTPException(status_code=404, detail=f"User '{username}' not found")
    await crons.state_backend.delete_user(username)
    return {"status": "success", "message": f"User '{username}' deleted"} 