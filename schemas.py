from pydantic import BaseModel
from typing import Optional, List, Dict

class JobCreateRequest(BaseModel):
    name: str
    expr: str
    tags: Optional[List] = None
    code: str
    is_async: bool = False
    dependencies: Optional[List] = None
    on_success: Optional[List] = None
    on_failure: Optional[List] = None
    parameters_schema: Optional[Dict] = None

class JobUpdateRequest(BaseModel):
    expr: Optional[str] = None
    tags: Optional[List] = None
    code: Optional[str] = None
    is_async: Optional[bool] = None
    dependencies: Optional[List] = None
    on_success: Optional[List] = None
    on_failure: Optional[List] = None
    parameters_schema: Optional[Dict] = None
    class Config:
        extra = "forbid"

class Token(BaseModel):
    access_token: str
    token_type: str

class User(BaseModel):
    username: str
    role: str

class UserRoleUpdateRequest(BaseModel):
    new_role: str 