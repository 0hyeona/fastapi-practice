"""회원가입 요청을 검사하고 응답에 포함할 정보를 정합니다."""

from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, EmailStr, Field, SecretStr, StringConstraints


class SignupRequest(BaseModel):
    user_id: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=50)]
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=50)]
    email: EmailStr = Field(max_length=255)
    password: SecretStr = Field(min_length=8, max_length=128)


class SignupResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: str
    name: str
    email: EmailStr
    account_status: str
    created_at: datetime


class LoginRequest(BaseModel):
    user_id: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=50)]
    password: SecretStr = Field(min_length=1, max_length=128)


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: SignupResponse
