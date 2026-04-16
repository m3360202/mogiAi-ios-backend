"""
初始化练习题目和成就数据
"""
import asyncio
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import async_session_maker
from app.models.practice import PracticeTopic, TopicCategory
from app.models.achievement import Achievement, AchievementCategory, AchievementRarity


async def init_practice_topics(db: AsyncSession):
    """初始化练习题目"""
    
    # 初级篇题目
    beginner_topics = [
        {
            "title": "自己紹介",
            "category": TopicCategory.BEGINNER,
            "icon": "account",
            "dimension": "内容",
            "min_duration": 120,
            "max_duration": 180,
            "recommended_duration": "2-3分",
            "description": "自分の経歴や強みを簡潔に紹介してください",
            "sort_order": 1
        },
        {
            "title": "志望動機",
            "category": TopicCategory.BEGINNER,
            "icon": "target",
            "dimension": "論理性",
            "min_duration": 180,
            "max_duration": 300,
            "recommended_duration": "3-5分",
            "description": "なぜこの企業を志望するのか、論理的に説明してください",
            "sort_order": 2
        },
        {
            "title": "強みと弱み",
            "category": TopicCategory.BEGINNER,
            "icon": "arm-flex",
            "dimension": "態度",
            "min_duration": 120,
            "max_duration": 180,
            "recommended_duration": "2-3分",
            "description": "自分の強みと弱みを誠実に説明してください",
            "sort_order": 3
        },
        {
            "title": "プロジェクト経験",
            "category": TopicCategory.BEGINNER,
            "icon": "briefcase",
            "dimension": "専門性",
            "min_duration": 300,
            "max_duration": 420,
            "recommended_duration": "5-7分",
            "description": "これまでのプロジェクト経験を具体的に説明してください",
            "sort_order": 4
        },
        {
            "title": "キャリアプラン",
            "category": TopicCategory.BEGINNER,
            "icon": "chart-timeline-variant",
            "dimension": "表現力",
            "min_duration": 180,
            "max_duration": 300,
            "recommended_duration": "3-5分",
            "description": "将来のキャリアビジョンを説明してください",
            "sort_order": 5
        },
        {
            "title": "ストレス対処法",
            "category": TopicCategory.BEGINNER,
            "icon": "meditation",
            "dimension": "流暢度",
            "min_duration": 120,
            "max_duration": 180,
            "recommended_duration": "2-3分",
            "description": "ストレスをどのように対処するか説明してください",
            "sort_order": 6
        }
    ]
    
    # 应用篇题目
    advanced_topics = [
        {
            "title": "チームでの困難な状況",
            "category": TopicCategory.ADVANCED,
            "icon": "account-group",
            "min_duration": 180,
            "max_duration": 300,
            "recommended_duration": "3-5分",
            "description": "チームで困難な状況に直面した経験を説明してください",
            "sort_order": 7
        },
        {
            "title": "失敗から学んだこと",
            "category": TopicCategory.ADVANCED,
            "icon": "school",
            "min_duration": 180,
            "max_duration": 300,
            "recommended_duration": "3-5分",
            "description": "失敗経験とそこから学んだことを説明してください",
            "sort_order": 8
        },
        {
            "title": "リーダーシップ経験",
            "category": TopicCategory.ADVANCED,
            "icon": "shield-crown",
            "min_duration": 180,
            "max_duration": 300,
            "recommended_duration": "3-5分",
            "description": "リーダーシップを発揮した経験を説明してください",
            "sort_order": 9
        },
        {
            "title": "技術的な課題の解決",
            "category": TopicCategory.ADVANCED,
            "icon": "code-tags",
            "min_duration": 300,
            "max_duration": 420,
            "recommended_duration": "5-7分",
            "description": "技術的な課題をどのように解決したか説明してください",
            "sort_order": 10
        },
        {
            "title": "意見の対立への対応",
            "category": TopicCategory.ADVANCED,
            "icon": "comment-alert",
            "min_duration": 180,
            "max_duration": 300,
            "recommended_duration": "3-5分",
            "description": "意見の対立をどのように解決したか説明してください",
            "sort_order": 11
        },
        {
            "title": "時間管理の工夫",
            "category": TopicCategory.ADVANCED,
            "icon": "clock-check",
            "min_duration": 120,
            "max_duration": 180,
            "recommended_duration": "2-3分",
            "description": "効率的な時間管理の方法を説明してください",
            "sort_order": 12
        },
        {
            "title": "イノベーション提案",
            "category": TopicCategory.ADVANCED,
            "icon": "lightbulb-on",
            "min_duration": 180,
            "max_duration": 300,
            "recommended_duration": "3-5分",
            "description": "新しいアイデアや改善提案について説明してください",
            "sort_order": 13
        },
        {
            "title": "グローバル協働経験",
            "category": TopicCategory.ADVANCED,
            "icon": "earth",
            "min_duration": 180,
            "max_duration": 300,
            "recommended_duration": "3-5分",
            "description": "異文化チームでの協働経験を説明してください",
            "sort_order": 14
        }
    ]
    
    # 插入数据
    for topic_data in beginner_topics + advanced_topics:
        # 检查是否已存在
        result = await db.execute(
            select(PracticeTopic).where(PracticeTopic.title == topic_data["title"])
        )
        existing = result.scalar_one_or_none()
        
        if not existing:
            topic = PracticeTopic(**topic_data)
            db.add(topic)
    
    await db.commit()
    print(f"✅ 初始化了 {len(beginner_topics + advanced_topics)} 个练习题目")


async def init_achievements(db: AsyncSession):
    """初始化成就数据"""
    
    achievements_data = [
        # 练习相关成就
        {
            "title": "初めの一歩",
            "description": "初めて練習を完了しました",
            "icon": "foot-print",
            "category": AchievementCategory.PRACTICE,
            "rarity": AchievementRarity.COMMON,
            "unlock_criteria": {"type": "practice_count", "value": 1},
            "reward_points": 10,
            "sort_order": 1
        },
        {
            "title": "練習熱心",
            "description": "10回の練習を完了しました",
            "icon": "fire",
            "category": AchievementCategory.PRACTICE,
            "rarity": AchievementRarity.COMMON,
            "unlock_criteria": {"type": "practice_count", "value": 10},
            "reward_points": 50,
            "sort_order": 2
        },
        {
            "title": "練習マスター",
            "description": "50回の練習を完了しました",
            "icon": "trophy",
            "category": AchievementCategory.PRACTICE,
            "rarity": AchievementRarity.RARE,
            "unlock_criteria": {"type": "practice_count", "value": 50},
            "reward_points": 200,
            "sort_order": 3
        },
        {
            "title": "練習の達人",
            "description": "100回の練習を完了しました",
            "icon": "crown",
            "category": AchievementCategory.PRACTICE,
            "rarity": AchievementRarity.EPIC,
            "unlock_criteria": {"type": "practice_count", "value": 100},
            "reward_points": 500,
            "sort_order": 4
        },
        
        # 分数相关成就
        {
            "title": "優秀な成績",
            "description": "80点以上を獲得しました",
            "icon": "star",
            "category": AchievementCategory.SCORE,
            "rarity": AchievementRarity.COMMON,
            "unlock_criteria": {"type": "score_threshold", "value": 80},
            "reward_points": 30,
            "sort_order": 5
        },
        {
            "title": "完璧なパフォーマンス",
            "description": "90点以上を獲得しました",
            "icon": "star-circle",
            "category": AchievementCategory.SCORE,
            "rarity": AchievementRarity.RARE,
            "unlock_criteria": {"type": "score_threshold", "value": 90},
            "reward_points": 100,
            "sort_order": 6
        },
        {
            "title": "伝説の面接者",
            "description": "95点以上を獲得しました",
            "icon": "diamond",
            "category": AchievementCategory.SCORE,
            "rarity": AchievementRarity.LEGENDARY,
            "unlock_criteria": {"type": "score_threshold", "value": 95},
            "reward_points": 300,
            "sort_order": 7
        },
        
        # 连续练习成就
        {
            "title": "継続は力なり",
            "description": "3日連続で練習しました",
            "icon": "calendar-check",
            "category": AchievementCategory.STREAK,
            "rarity": AchievementRarity.COMMON,
            "unlock_criteria": {"type": "streak_days", "value": 3},
            "reward_points": 20,
            "sort_order": 8
        },
        {
            "title": "一週間の努力",
            "description": "7日連続で練習しました",
            "icon": "calendar-star",
            "category": AchievementCategory.STREAK,
            "rarity": AchievementRarity.RARE,
            "unlock_criteria": {"type": "streak_days", "value": 7},
            "reward_points": 100,
            "sort_order": 9
        },
        {
            "title": "月間チャンピオン",
            "description": "30日連続で練習しました",
            "icon": "medal",
            "category": AchievementCategory.STREAK,
            "rarity": AchievementRarity.EPIC,
            "unlock_criteria": {"type": "streak_days", "value": 30},
            "reward_points": 500,
            "sort_order": 10
        },
        
        # 精通相关成就
        {
            "title": "内容マスター",
            "description": "内容次元で金レベルに達成しました",
            "icon": "text-box-check",
            "category": AchievementCategory.MASTERY,
            "rarity": AchievementRarity.RARE,
            "unlock_criteria": {"type": "dimension_mastery", "dimension": "content", "level": "gold"},
            "reward_points": 150,
            "sort_order": 11
        },
        {
            "title": "表現力マスター",
            "description": "表現力次元で金レベルに達成しました",
            "icon": "account-voice",
            "category": AchievementCategory.MASTERY,
            "rarity": AchievementRarity.RARE,
            "unlock_criteria": {"type": "dimension_mastery", "dimension": "expression", "level": "gold"},
            "reward_points": 150,
            "sort_order": 12
        },
        {
            "title": "全次元マスター",
            "description": "すべての次元で金レベルに達成しました",
            "icon": "crown-circle",
            "category": AchievementCategory.MASTERY,
            "rarity": AchievementRarity.LEGENDARY,
            "unlock_criteria": {"type": "all_dimensions_mastery", "level": "gold"},
            "reward_points": 1000,
            "sort_order": 13,
            "is_hidden": True
        }
    ]
    
    # 插入数据
    for achievement_data in achievements_data:
        # 检查是否已存在
        result = await db.execute(
            select(Achievement).where(Achievement.title == achievement_data["title"])
        )
        existing = result.scalar_one_or_none()
        
        if not existing:
            achievement = Achievement(**achievement_data)
            db.add(achievement)
    
    await db.commit()
    print(f"✅ 初始化了 {len(achievements_data)} 个成就")


async def main():
    """主函数"""
    async with async_session_maker() as db:
        print("开始初始化数据...")
        await init_practice_topics(db)
        await init_achievements(db)
        print("✅ 数据初始化完成！")


if __name__ == "__main__":
    asyncio.run(main())

