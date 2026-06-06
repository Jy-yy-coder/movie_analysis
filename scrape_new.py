"""
采集新增电影数据
只采集之前未采集的新增电影 + 重新采集哪吒之魔童闹海（仅75条）
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from config import PROGRESS_FILE, RAW_DATA_DIR

# 新增电影列表（名称, 年份）
NEW_MOVIES = [
    # 2021年新增
    ("熊出没·狂野大陆", 2021),
    ("新神榜：哪吒重生", 2021),
    # 2022年新增
    ("狙击手", 2022),
    ("熊出没·重返地球", 2022),
    ("喜羊羊与灰太狼之筐出未来", 2022),
    # 2023年新增
    ("深海", 2023),
    ('熊出没·伴我"熊芯"', 2023),
    # 2024年新增
    ("我们一起摇太阳", 2024),
    ("红毯先生", 2024),
    # 2025年新增（哪吒重新采集）
    ("哪吒之魔童闹海", 2025),
    ("射雕英雄传：侠之大者", 2025),
    ("蛟龙行动", 2025),
    # 2026年新增
    ("夜王", 2026),
    ("星河如梦", 2026),
]


def reset_nezha_progress():
    """清除哪吒之魔童闹海的进度记录，使其可以重新采集"""
    if PROGRESS_FILE.exists():
        with open(PROGRESS_FILE, "r", encoding="utf-8") as f:
            progress = json.load(f)

        # 找到哪吒相关的 movie_id 并清除其进度
        keys_to_remove = []
        for key in progress:
            if isinstance(progress[key], dict):
                # 检查是否是哪吒的记录（通过scraped_ids中的comment_id无法判断，
                # 但可以通过movie_cache找到ID）
                pass

        # 从movie_cache.json获取哪吒的豆瓣ID
        cache_file = RAW_DATA_DIR / "movie_cache.json"
        nezha_id = None
        if cache_file.exists():
            with open(cache_file, "r", encoding="utf-8") as f:
                cache = json.load(f)
            for key, val in cache.items():
                if "哪吒之魔童闹海" in key or "魔童闹海" in key:
                    nezha_id = str(val.get("id", ""))
                    break

        if nezha_id and nezha_id in progress:
            del progress[nezha_id]
            with open(PROGRESS_FILE, "w", encoding="utf-8") as f:
                json.dump(progress, f, ensure_ascii=False, indent=2)
            print(f"  已清除哪吒之魔童闹海(ID:{nezha_id})的进度记录")
        else:
            print(f"  未找到哪吒进度记录(可能是首次采集或ID未匹配)")


if __name__ == "__main__":
    print(f"将采集 {len(NEW_MOVIES)} 部新增电影:")
    for n, y in NEW_MOVIES:
        print(f"  - {n} ({y})")

    # 清除哪吒进度，使其可以重新采集
    print("\n清除哪吒之魔童闹海的旧进度...")
    reset_nezha_progress()
    print()

    from scraper.douban_review import run_direct
    names = [m[0] for m in NEW_MOVIES]
    years = [m[1] for m in NEW_MOVIES]
    run_direct(movies=names, years=years)
