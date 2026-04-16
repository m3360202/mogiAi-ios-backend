"""
企业模板相关API端点
"""
from typing import List
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.schemas.corporate import CorporateTemplateCreate, CorporateTemplateUpdate, CorporateTemplateResponse
from app.services.corporate_service import CorporateService
from app.api.dependencies import get_current_user
from app.models.user import User


router = APIRouter()


@router.post("/templates", response_model=CorporateTemplateResponse, status_code=status.HTTP_201_CREATED)
async def create_template(
    template_data: CorporateTemplateCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """创建企业面试模板"""
    corporate_service = CorporateService(db)
    template = await corporate_service.create_template(current_user.id, template_data)
    return template


@router.get("/templates", response_model=List[CorporateTemplateResponse])
async def list_templates(
    skip: int = 0,
    limit: int = 20,
    include_public: bool = True,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """获取企业模板列表"""
    corporate_service = CorporateService(db)
    templates = await corporate_service.get_user_templates(
        user_id=current_user.id,
        skip=skip,
        limit=limit,
        include_public=include_public
    )
    return templates


@router.get("/templates/{template_id}", response_model=CorporateTemplateResponse)
async def get_template(
    template_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """获取模板详情"""
    corporate_service = CorporateService(db)
    template = await corporate_service.get_template(template_id, current_user.id)
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")
    return template


@router.put("/templates/{template_id}", response_model=CorporateTemplateResponse)
async def update_template(
    template_id: UUID,
    template_data: CorporateTemplateUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """更新企业模板"""
    corporate_service = CorporateService(db)
    template = await corporate_service.update_template(template_id, current_user.id, template_data)
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")
    return template


@router.delete("/templates/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_template(
    template_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """删除企业模板"""
    corporate_service = CorporateService(db)
    await corporate_service.delete_template(template_id, current_user.id)
    return None

