"""
企业模板服务
"""
from typing import List, Optional
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_
from fastapi import HTTPException

from app.models.corporate import CorporateTemplate
from app.schemas.corporate import CorporateTemplateCreate, CorporateTemplateUpdate


class CorporateService:
    """企业服务"""
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def create_template(
        self, 
        user_id: UUID, 
        template_data: CorporateTemplateCreate
    ) -> CorporateTemplate:
        """创建企业模板"""
        template = CorporateTemplate(
            user_id=user_id,
            company_name=template_data.company_name,
            company_website=template_data.company_website,
            company_description=template_data.company_description,
            position_title=template_data.position_title,
            position_description=template_data.position_description,
            required_skills={"skills": template_data.required_skills or []},
            interview_stages={"stages": template_data.interview_stages or []},
            custom_questions={"questions": template_data.custom_questions or []},
            evaluation_criteria=template_data.evaluation_criteria or {},
            is_public=template_data.is_public
        )
        
        self.db.add(template)
        await self.db.commit()
        await self.db.refresh(template)
        
        return template
    
    async def get_template(self, template_id: UUID, user_id: UUID) -> Optional[CorporateTemplate]:
        """获取模板详情"""
        result = await self.db.execute(
            select(CorporateTemplate).where(
                CorporateTemplate.id == template_id,
                or_(
                    CorporateTemplate.user_id == user_id,
                    CorporateTemplate.is_public == True
                )
            )
        )
        return result.scalar_one_or_none()
    
    async def get_user_templates(
        self, 
        user_id: UUID, 
        skip: int = 0, 
        limit: int = 20,
        include_public: bool = True
    ) -> List[CorporateTemplate]:
        """获取用户的模板列表"""
        query = select(CorporateTemplate)
        
        if include_public:
            query = query.where(
                or_(
                    CorporateTemplate.user_id == user_id,
                    CorporateTemplate.is_public == True
                )
            )
        else:
            query = query.where(CorporateTemplate.user_id == user_id)
        
        query = query.order_by(CorporateTemplate.created_at.desc()).offset(skip).limit(limit)
        
        result = await self.db.execute(query)
        return result.scalars().all()
    
    async def update_template(
        self, 
        template_id: UUID, 
        user_id: UUID, 
        template_data: CorporateTemplateUpdate
    ) -> Optional[CorporateTemplate]:
        """更新企业模板"""
        template = await self.get_template(template_id, user_id)
        
        if not template or template.user_id != user_id:
            return None
        
        # 更新字段
        update_data = template_data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            if field in ["required_skills", "interview_stages", "custom_questions"]:
                if value is not None:
                    setattr(template, field, {field[:-1] if field.endswith('s') else field: value})
            else:
                setattr(template, field, value)
        
        await self.db.commit()
        await self.db.refresh(template)
        
        return template
    
    async def delete_template(self, template_id: UUID, user_id: UUID):
        """删除企业模板"""
        template = await self.get_template(template_id, user_id)
        
        if not template or template.user_id != user_id:
            raise HTTPException(status_code=404, detail="Template not found")
        
        await self.db.delete(template)
        await self.db.commit()

