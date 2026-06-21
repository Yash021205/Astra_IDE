"""Pydantic schemas for auth endpoints."""
from typing import Optional
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
    avatar_url:     Optional[str] = None
    is_admin:       bool = False
    github_login:   Optional[str] = None  # None means GitHub not linked

    class Config:
        from_attributes = True


class UpdateProfile(BaseModel):
    avatar_url: Optional[str] = Field(default=None, max_length=512)


class Token(BaseModel):
    access_token: str
    token_type:   str = "bearer"
    user:         UserOut
