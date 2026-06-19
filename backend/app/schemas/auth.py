"""Pydantic schemas for auth endpoints."""
from pydantic import BaseModel, EmailStr, Field


class UserCreate(BaseModel):
    email:    EmailStr
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=8, max_length=128)


class UserLogin(BaseModel):
    username_or_email: str
    password:          str


class UserOut(BaseModel):
    id:             int
    email:          EmailStr
    username:       str
    trust_score:    float
    preferred_lang: str

    class Config:
        from_attributes = True


class Token(BaseModel):
    access_token: str
    token_type:   str = "bearer"
    user:         UserOut
