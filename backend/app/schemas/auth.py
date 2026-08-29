from pydantic import BaseModel


class LoginRequest(BaseModel):
    username: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: str
    display_name: str
    role: str


class UserOut(BaseModel):
    username: str
    display_name: str
    role: str
