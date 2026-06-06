"""
全局配置文件
============
项目路径、数据库、常量等统一配置
"""

from pathlib import Path

# ======================== 路径配置 ========================

# 项目根目录
BASE_DIR = Path(__file__).resolve().parent

# 数据目录
DATA_DIR = BASE_DIR / "data"
RAW_DATA_DIR = DATA_DIR / "raw"
CLEANED_DATA_DIR = DATA_DIR / "cleaned"
ANALYSIS_DATA_DIR = DATA_DIR / "analysis"
DATABASE_DIR = DATA_DIR / "database"

# 浏览器持久化数据目录（保存登录状态）
BROWSER_DATA_DIR = BASE_DIR / "browser_data"

# 数据库文件
DATABASE_PATH = DATABASE_DIR / "movie.db"

# 爬取进度文件
PROGRESS_FILE = RAW_DATA_DIR / "scrape_progress.json"

# 电影搜索结果缓存文件（避免重复搜索）
MOVIE_CACHE_FILE = RAW_DATA_DIR / "movie_cache.json"

# ======================== 自动创建目录 ========================

for _dir in [RAW_DATA_DIR, CLEANED_DATA_DIR, ANALYSIS_DATA_DIR,
             DATABASE_DIR, BROWSER_DATA_DIR]:
    _dir.mkdir(parents=True, exist_ok=True)

# ======================== 豆瓣配置 ========================

DOUBAN_BASE_URL = "https://movie.douban.com"
DOUBAN_LOGIN_URL = "https://accounts.douban.com/passport/login"
DOUBAN_SEARCH_URL = "https://search.douban.com/movie/subject_search"

# 每页评论数（豆瓣固定 20 条）
COMMENTS_PER_PAGE = 20

# 请求延时范围（秒）—— 页面间翻页
DELAY_MIN = 3.0
DELAY_MAX = 7.0

# 搜索页延时（秒）
SEARCH_DELAY_MIN = 2.0
SEARCH_DELAY_MAX = 4.0

# 最大连续空页数（超过则停止）
MAX_EMPTY_PAGES = 3

# 每部电影最少采集评论数
MIN_REVIEWS_PER_MOVIE = 500

# ======================== 2021-2026 春节档电影 ========================
# 格式: { 年份: [电影名称列表] }
# ID 由程序自动搜索获取，无需手动填写

SPRING_FESTIVAL_MOVIES = {
    2021: [
        "你好，李焕英",
        "唐人街探案3",
        "刺杀小说家",
        "人潮汹涌",
        "熊出没·狂野大陆",
        "新神榜：哪吒重生",
    ],
    2022: [
        "长津湖之水门桥",
        "这个杀手不太冷静",
        "奇迹·笨小孩",
        "四海",
        "狙击手",
        "熊出没·重返地球",
        "喜羊羊与灰太狼之筐出未来",
    ],
    2023: [
        "满江红",
        "流浪地球2",
        "无名",
        "交换人生",
        "深海",
        "熊出没·伴我\"熊芯\"",
    ],
    2024: [
        "热辣滚烫",
        "飞驰人生2",
        "第二十条",
        "熊出没·逆转时空",
        "我们一起摇太阳",
        "红毯先生",
    ],
    2025: [
        "哪吒之魔童闹海",
        "唐探1900",
        "封神第二部：战火西岐",
        "熊出没·重启未来",
        "射雕英雄传：侠之大者",
        "蛟龙行动",
    ],
    2026: [
        "飞驰人生3",
        "惊蛰无声",
        "镖人",
        "熊出没：年年有熊",
        "夜王",
        "星河如梦",
    ],
}

# CSV 字段名
CSV_FIELDNAMES = [
    "评论ID", "电影名称", "上映年份", "用户昵称", "用户评分",
    "评论内容", "评论时间", "点赞数"
]
