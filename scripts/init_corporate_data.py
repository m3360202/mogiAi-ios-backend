"""
企业数据初始化脚本
合法方式：使用公开信息手动整理，不使用爬虫

数据来源：
- 企业官网公开信息
- 公开的招聘信息（参考但不爬取）
- 手动整理的热门企业和职位
"""
import asyncio
import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from app.models.corporate import CorporateTemplate
from app.core.config import settings
from uuid import uuid4


# 预设企业数据（基于公开信息手动整理）
PRESET_COMPANIES = [
    {
        "company_name": "楽天株式会社",
        "company_website": "https://corp.rakuten.co.jp",
        "company_description": "日本最大級のインターネットサービス企業。EC、金融、モバイル、旅行など多角的な事業を展開。",
        "positions": [
            {
                "position_title": "バックエンドエンジニア",
                "position_description": "大規模システムの設計・開発・運用。マイクロサービスアーキテクチャの構築。",
                "required_skills": ["Java", "Kotlin", "Spring Boot", "Docker", "Kubernetes", "AWS"],
                "interview_stages": ["書類選考", "技術面接（1次）", "技術面接（2次）", "最終面接"],
            },
            {
                "position_title": "フロントエンドエンジニア",
                "position_description": "ユーザー向けWebアプリケーションの開発。React/Vue.jsを使用したSPA開発。",
                "required_skills": ["JavaScript", "TypeScript", "React", "Vue.js", "Next.js", "Webpack"],
                "interview_stages": ["書類選考", "技術面接", "コーディングテスト", "最終面接"],
            },
            {
                "position_title": "データエンジニア",
                "position_description": "ビッグデータ処理パイプラインの構築・運用。機械学習モデルのインフラ構築。",
                "required_skills": ["Python", "Spark", "Airflow", "BigQuery", "TensorFlow", "Kubernetes"],
                "interview_stages": ["書類選考", "技術面接", "データ設計課題", "最終面接"],
            },
        ],
    },
    {
        "company_name": "メルカリ株式会社",
        "company_website": "https://about.mercari.com",
        "company_description": "フリマアプリ「メルカリ」を運営するスタートアップ。世界中で展開するマーケットプレイス事業。",
        "positions": [
            {
                "position_title": "バックエンドエンジニア",
                "position_description": "Go言語を使用した高負荷対応システムの開発。マイクロサービスアーキテクチャ。",
                "required_skills": ["Go", "gRPC", "Kubernetes", "AWS", "PostgreSQL", "Redis"],
                "interview_stages": ["書類選考", "技術面接（1次）", "技術面接（2次）", "最終面接"],
            },
            {
                "position_title": "iOSエンジニア",
                "position_description": "Swiftを使用したiOSアプリケーションの開発。パフォーマンス最適化。",
                "required_skills": ["Swift", "SwiftUI", "UIKit", "Combine", "RxSwift", "Core Data"],
                "interview_stages": ["書類選考", "技術面接", "コーディングテスト", "最終面接"],
            },
        ],
    },
    {
        "company_name": "サイバーエージェント株式会社",
        "company_website": "https://www.cyberagent.co.jp",
        "company_description": "インターネット広告、メディア事業、ゲーム事業を展開する総合IT企業。",
        "positions": [
            {
                "position_title": "フルスタックエンジニア",
                "position_description": "Webサービスのフロント・バックエンド開発。新規事業の立ち上げから開発まで。",
                "required_skills": ["Python", "JavaScript", "React", "Django", "AWS", "Docker"],
                "interview_stages": ["書類選考", "技術面接（1次）", "技術面接（2次）", "最終面接"],
            },
            {
                "position_title": "SRE/インフラエンジニア",
                "position_description": "クラウドインフラの設計・構築・運用。CI/CDパイプラインの構築。",
                "required_skills": ["Terraform", "Kubernetes", "AWS", "GCP", "Ansible", "Prometheus"],
                "interview_stages": ["書類選考", "技術面接", "インフラ設計課題", "最終面接"],
            },
        ],
    },
    {
        "company_name": "株式会社リクルート",
        "company_website": "https://www.recruit.co.jp",
        "company_description": "人材・教育・結婚・旅行・飲食など、生活に関わる様々なサービスを展開する大手企業。",
        "positions": [
            {
                "position_title": "バックエンドエンジニア",
                "position_description": "大規模Webサービスのバックエンド開発。API設計・実装。",
                "required_skills": ["Java", "Scala", "Spring Framework", "MySQL", "Redis", "AWS"],
                "interview_stages": ["書類選考", "技術面接（1次）", "技術面接（2次）", "最終面接"],
            },
            {
                "position_title": "データサイエンティスト",
                "position_description": "データ分析・機械学習モデルの開発。ビジネス課題へのデータ活用。",
                "required_skills": ["Python", "R", "SQL", "TensorFlow", "scikit-learn", "Tableau"],
                "interview_stages": ["書類選考", "技術面接", "データ分析課題", "最終面接"],
            },
        ],
    },
    {
        "company_name": "LINE株式会社",
        "company_website": "https://linecorp.com/ja",
        "company_description": "メッセージアプリ「LINE」を運営。SNS、金融、広告など様々なサービスを展開。",
        "positions": [
            {
                "position_title": "バックエンドエンジニア",
                "position_description": "高負荷対応システムの開発。メッセージング、ストリーミングサービスの開発。",
                "required_skills": ["Java", "Go", "Kotlin", "Spring Boot", "gRPC", "Kubernetes"],
                "interview_stages": ["書類選考", "技術面接（1次）", "技術面接（2次）", "最終面接"],
            },
            {
                "position_title": "Androidエンジニア",
                "position_description": "Kotlinを使用したAndroidアプリケーションの開発。パフォーマンス最適化。",
                "required_skills": ["Kotlin", "Java", "Android SDK", "RxJava", "Dagger", "Jetpack"],
                "interview_stages": ["書類選考", "技術面接", "コーディングテスト", "最終面接"],
            },
        ],
    },
    {
        "company_name": "株式会社DeNA",
        "company_website": "https://dena.com",
        "company_description": "ゲーム、モビリティ、ヘルスケアなどの事業を展開するインターネット企業。",
        "positions": [
            {
                "position_title": "フルスタックエンジニア",
                "position_description": "Webサービスの開発。フロントエンドからバックエンドまで幅広く対応。",
                "required_skills": ["Python", "JavaScript", "React", "Vue.js", "PostgreSQL", "AWS"],
                "interview_stages": ["書類選考", "技術面接", "コーディングテスト", "最終面接"],
            },
            {
                "position_title": "ゲームエンジニア",
                "position_description": "Unity/Cocos2d-xを使用したゲーム開発。サーバーサイド開発。",
                "required_skills": ["C++", "C#", "Unity", "Lua", "Python", "Redis"],
                "interview_stages": ["書類選考", "技術面接", "ゲーム開発課題", "最終面接"],
            },
        ],
    },
    {
        "company_name": "株式会社ワークスアプリケーションズ",
        "company_website": "https://www.worksap.co.jp",
        "company_description": "人事・給与システム「SmartHR」「Salary」を提供するHRテック企業。",
        "positions": [
            {
                "position_title": "バックエンドエンジニア",
                "position_description": "Ruby on Railsを使用したWebアプリケーション開発。API設計・実装。",
                "required_skills": ["Ruby", "Ruby on Rails", "PostgreSQL", "Redis", "Sidekiq", "AWS"],
                "interview_stages": ["書類選考", "技術面接", "コーディングテスト", "最終面接"],
            },
            {
                "position_title": "フロントエンドエンジニア",
                "position_description": "React/TypeScriptを使用したWebアプリケーション開発。UI/UX改善。",
                "required_skills": ["TypeScript", "React", "Redux", "Jest", "Storybook", "Webpack"],
                "interview_stages": ["書類選考", "技術面接", "コーディングテスト", "最終面接"],
            },
        ],
    },
    {
        "company_name": "freee株式会社",
        "company_website": "https://corp.freee.co.jp",
        "company_description": "クラウド会計ソフト「freee」を提供するフィンテック企業。",
        "positions": [
            {
                "position_title": "バックエンドエンジニア",
                "position_description": "Ruby on Railsを使用した会計システムの開発。財務計算ロジックの実装。",
                "required_skills": ["Ruby", "Ruby on Rails", "PostgreSQL", "Sidekiq", "AWS", "Docker"],
                "interview_stages": ["書類選考", "技術面接", "コーディングテスト", "最終面接"],
            },
        ],
    },
    {
        "company_name": "スタディサプリ",
        "company_website": "https://studysapuri.jp",
        "company_description": "リクルートが提供するオンライン学習サービス。教育テック事業。",
        "positions": [
            {
                "position_title": "バックエンドエンジニア",
                "position_description": "学習プラットフォームの開発。レコメンデーションシステムの実装。",
                "required_skills": ["Python", "Django", "PostgreSQL", "Redis", "AWS", "Docker"],
                "interview_stages": ["書類選考", "技術面接", "コーディングテスト", "最終面接"],
            },
        ],
    },
    {
        "company_name": "株式会社ミクシィ",
        "company_website": "https://mixi.co.jp",
        "company_description": "SNS「mixi」を運営。ゲーム、メディア事業も展開。",
        "positions": [
            {
                "position_title": "バックエンドエンジニア",
                "position_description": "大規模SNSシステムの開発。パフォーマンス最適化。",
                "required_skills": ["Perl", "Java", "MySQL", "Redis", "Memcached", "AWS"],
                "interview_stages": ["書類選考", "技術面接", "コーディングテスト", "最終面接"],
            },
        ],
    },
]


async def init_corporate_data():
    """初始化企业数据"""
    # 创建数据库连接
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    async with async_session() as session:
        try:
            # 使用系统用户ID（如果存在）或创建默认管理员用户
            # 这里假设有一个系统用户ID，如果没有需要先创建
            # 为了简化，我们使用一个固定的system_user_id
            from app.models.user import User
            from sqlalchemy import select
            
            # 查找或创建系统管理员用户（用于预设数据）
            result = await session.execute(
                select(User).where(User.email == "system@careerface.app")
            )
            system_user = result.scalar_one_or_none()
            
            if not system_user:
                print("[Init] System user not found, creating...")
                # 创建系统用户（仅用于预设数据）
                system_user = User(
                    id=uuid4(),
                    email="system@careerface.app",
                    full_name="System Admin",
                    is_active=True,
                    is_verified=True,
                )
                session.add(system_user)
                await session.flush()
                print(f"[Init] ✓ Created system user: {system_user.id}")
            else:
                print(f"[Init] ✓ Using existing system user: {system_user.id}")
            
            # 检查是否已有预设数据
            result = await session.execute(
                select(CorporateTemplate).where(CorporateTemplate.user_id == system_user.id)
            )
            existing_templates = result.scalars().all()
            
            if existing_templates:
                print(f"[Init] ⚠️ Found {len(existing_templates)} existing templates")
                response = input("Do you want to delete existing templates and re-initialize? (y/N): ")
                if response.lower() == 'y':
                    for template in existing_templates:
                        await session.delete(template)
                    await session.commit()
                    print("[Init] ✓ Deleted existing templates")
                else:
                    print("[Init] Keeping existing templates, skipping initialization")
                    return
            
            # 创建预设数据
            count = 0
            for company_data in PRESET_COMPANIES:
                for position_data in company_data["positions"]:
                    template = CorporateTemplate(
                        user_id=system_user.id,
                        company_name=company_data["company_name"],
                        company_website=company_data.get("company_website"),
                        company_description=company_data.get("company_description"),
                        position_title=position_data["position_title"],
                        position_description=position_data.get("position_description"),
                        required_skills={"skills": position_data.get("required_skills", [])},
                        interview_stages={"stages": position_data.get("interview_stages", [])},
                        custom_questions={"questions": []},  # 可以后续添加
                        evaluation_criteria={},  # 默认评价标准
                        is_active=True,
                        is_public=True,  # 预设数据设为公开，所有用户可见
                    )
                    session.add(template)
                    count += 1
                    print(f"[Init] ✓ Created template: {company_data['company_name']} - {position_data['position_title']}")
            
            await session.commit()
            print(f"\n[Init] ✅ Successfully initialized {count} corporate templates!")
            print(f"[Init] All templates are set as public (is_public=True)")
            
        except Exception as e:
            await session.rollback()
            print(f"[Init] ❌ Error: {e}")
            import traceback
            traceback.print_exc()
            raise
        finally:
            await engine.dispose()


if __name__ == "__main__":
    print("=" * 60)
    print("Corporate Data Initialization Script")
    print("=" * 60)
    print("\nThis script will create preset corporate templates")
    print("based on publicly available information.")
    print("\n⚠️  Data Source: Manual compilation from public sources")
    print("⚠️  Legal: No web scraping involved")
    print("=" * 60)
    print()
    
    asyncio.run(init_corporate_data())



