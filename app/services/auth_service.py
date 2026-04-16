"""
Authentication Service with Supabase JWT Verification
"""
from datetime import datetime, timedelta
from typing import Optional
import jwt
from jose import JWTError
from passlib.context import CryptContext
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from fastapi import HTTPException, status

from app.core.config import settings
from app.core.supabase import supabase
from app.models.user import User
from app.schemas.user import UserCreate, UserLogin, Token


# Password hashing context (for legacy support)
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class AuthService:
    """Authentication Service with Supabase Integration"""
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    @staticmethod
    def verify_supabase_token(token: str) -> dict:
        """
        Verify Supabase JWT token
        
        Args:
            token: JWT token from Supabase
            
        Returns:
            Decoded token payload
            
        Raises:
            HTTPException: If token is invalid
        """
        try:
            # Decode and verify JWT token using Supabase JWT secret
            payload = jwt.decode(
                token,
                settings.SUPABASE_JWT_SECRET,
                algorithms=["HS256"],
                audience="authenticated"
            )
            
            user_id = payload.get("sub")
            if user_id is None:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid authentication credentials",
                    headers={"WWW-Authenticate": "Bearer"},
                )
            
            return payload
            
        except jwt.ExpiredSignatureError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token has expired",
                headers={"WWW-Authenticate": "Bearer"},
            )
        except (JWTError, Exception) as e:  # 使用 jose 的 JWTError
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Could not validate credentials: {str(e)}",
                headers={"WWW-Authenticate": "Bearer"},
            )
    
    async def get_or_create_user_from_token(self, token_payload: dict) -> User:
        """
        Get or create user from Supabase token payload
        
        Args:
            token_payload: Decoded JWT token payload
            
        Returns:
            User instance
            
        Raises:
            HTTPException: If user creation fails
        """
        user_id = token_payload.get("sub")
        email = token_payload.get("email")
        user_metadata = token_payload.get("user_metadata", {})
        
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token: missing user ID"
            )
        
        # Try to get existing user by supabase_id
        result = await self.db.execute(
            select(User).where(User.supabase_id == user_id)
        )
        user = result.scalar_one_or_none()
        
        if user:
            # Update last login
            user.last_login = datetime.utcnow()
            await self.db.commit()
            await self.db.refresh(user)
            return user
        
        # If user not found by supabase_id, try to find by email and update supabase_id
        if email:
            result = await self.db.execute(
                select(User).where(User.email == email)
            )
            existing_user = result.scalar_one_or_none()
            
            if existing_user:
                # Update existing user with supabase_id
                existing_user.supabase_id = user_id
                existing_user.last_login = datetime.utcnow()
                await self.db.commit()
                await self.db.refresh(existing_user)
                return existing_user
        
        # Create new user if not exists
        try:
            new_user = User(
                supabase_id=user_id,
                email=email or f"user_{user_id}@temp.com",  # Fallback email if missing
                full_name=user_metadata.get("full_name", ""),
                phone=user_metadata.get("phone", ""),
                preferred_language=user_metadata.get("preferred_language", "ja"),
                is_active=True,
                is_verified=True,  # Supabase Auth users are verified
                last_login=datetime.utcnow()
            )
            
            self.db.add(new_user)
            await self.db.commit()
            await self.db.refresh(new_user)
            
            return new_user
        except Exception as e:
            await self.db.rollback()
            # If creation fails, try to get user again (might have been created by another request)
            result = await self.db.execute(
                select(User).where(User.supabase_id == user_id)
            )
            user = result.scalar_one_or_none()
            if user:
                return user
            # If still not found, raise error
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to create user: {str(e)}"
            )
    
    async def get_user_by_supabase_id(self, supabase_id: str) -> Optional[User]:
        """Get user by Supabase ID"""
        result = await self.db.execute(
            select(User).where(User.supabase_id == supabase_id)
        )
        return result.scalar_one_or_none()
    
    async def get_user_by_email(self, email: str) -> Optional[User]:
        """Get user by email"""
        result = await self.db.execute(select(User).where(User.email == email))
        return result.scalar_one_or_none()
    
    async def update_user_profile(
        self, 
        user: User, 
        full_name: Optional[str] = None,
        phone: Optional[str] = None,
        preferred_language: Optional[str] = None
    ) -> User:
        """Update user profile"""
        if full_name is not None:
            user.full_name = full_name
        if phone is not None:
            user.phone = phone
        if preferred_language is not None:
            user.preferred_language = preferred_language
        
        user.updated_at = datetime.utcnow()
        await self.db.commit()
        await self.db.refresh(user)
        
        return user
    
    # Legacy methods for backward compatibility (if needed)
    @staticmethod
    def verify_password(plain_password: str, hashed_password: str) -> bool:
        """Verify password (legacy)"""
        return pwd_context.verify(plain_password, hashed_password)
    
    @staticmethod
    def get_password_hash(password: str) -> str:
        """Get password hash (legacy)"""
        return pwd_context.hash(password)
    
    @staticmethod
    def create_access_token(user_id: str, expires_delta: Optional[timedelta] = None) -> str:
        """Create access token (legacy)"""
        if expires_delta:
            expire = datetime.utcnow() + expires_delta
        else:
            expire = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        
        to_encode = {"sub": str(user_id), "exp": expire}
        encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
        return encoded_jwt
    
    async def register_user(self, user_data: UserCreate) -> User:
        """
        Register new user (legacy method)
        Note: With Supabase, registration should be done on the frontend
        This is kept for backward compatibility
        """
        existing_user = await self.get_user_by_email(user_data.email)
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already registered"
            )
        
        hashed_password = self.get_password_hash(user_data.password)
        new_user = User(
            email=user_data.email,
            hashed_password=hashed_password,
            full_name=user_data.full_name,
            phone=user_data.phone,
            preferred_language=user_data.preferred_language
        )
        
        self.db.add(new_user)
        await self.db.commit()
        await self.db.refresh(new_user)
        
        return new_user
