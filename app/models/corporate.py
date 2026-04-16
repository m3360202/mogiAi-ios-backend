"""
企业模板数据模型
"""
from datetime import datetime
from uuid import uuid4
from sqlalchemy import String, DateTime, Text, Boolean, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID, JSONB

from app.core.database import Base


class CorporateTemplate(Base):
    """企业面试模板模型"""
    __tablename__ = "corporate_templates"
    
    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    
    # 企业信息
    company_name: Mapped[str] = mapped_column(String(100), nullable=False)
    company_website: Mapped[str] = mapped_column(String(255), nullable=True)
    company_description: Mapped[str] = mapped_column(Text, nullable=True)
    
    # 职位信息
    position_title: Mapped[str] = mapped_column(String(100), nullable=False)
    position_description: Mapped[str] = mapped_column(Text, nullable=True)
    required_skills: Mapped[dict] = mapped_column(JSONB, nullable=True)
    
    # 面试配置
    interview_stages: Mapped[dict] = mapped_column(JSONB, nullable=True)  # 面试阶段配置
    custom_questions: Mapped[dict] = mapped_column(JSONB, nullable=True)  # 自定义问题
    evaluation_criteria: Mapped[dict] = mapped_column(JSONB, nullable=True)  # 评价标准
    
    # 模板状态
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_public: Mapped[bool] = mapped_column(Boolean, default=False)
    
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # 关系
    user: Mapped["User"] = relationship("User", back_populates="corporate_templates")
    
    def __repr__(self):
        return f"<CorporateTemplate {self.company_name} - {self.position_title}>"

