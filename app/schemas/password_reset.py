import re
from pydantic import BaseModel, EmailStr, Field, SecretStr, model_validator


class EmailRequest(BaseModel):
    email: EmailStr = Field(max_length=255)


class MessageResponse(BaseModel):
    message: str


class CodeRequest(EmailRequest):
    code: str = Field(pattern=r"^[0-9]{6}$")


class CodeResponse(BaseModel):
    reset_token: str
    expires_in: int


class ResetRequest(BaseModel):
    reset_token: SecretStr = Field(min_length=1, max_length=128)
    new_password: SecretStr = Field(min_length=8, max_length=16)
    confirm_password: SecretStr = Field(min_length=8, max_length=16)

    @model_validator(mode="after")
    def validate_password(self):
        password = self.new_password.get_secret_value()
        if password != self.confirm_password.get_secret_value():
            raise ValueError("비밀번호가 일치하지 않습니다.")
        if not (re.search(r"[A-Za-z]", password) and re.search(r"[0-9]", password)
                and re.search(r"[^A-Za-z0-9\s]", password)) or any(c.isspace() for c in password):
            raise ValueError("비밀번호는 영문, 숫자, 특수문자를 조합한 8~16자여야 합니다.")
        return self
