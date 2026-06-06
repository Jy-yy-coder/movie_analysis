"""
重采失败的电影 + 补采数据不足的电影
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from config import PROGRESS_FILE, RAW_DATA_DIR

# 需要重新采集的电影
RETRY_MOVIES = [
    # 数据不足，需补采
    ("夜王", 2026),  # 仅197条，被限制
]


def reset_progress():
    """清除需重采电影的进度记录"""
    if not PROGRESS_FILE.exists():
        return

    with open(PROGRESS_FILE, "r", encoding="utf-8") as f:
        progress = json.load(f)

    # 获取所有相关电影的豆瓣ID（从缓存）
    cache_file = RAW_DATA_DIR / "movie_cache.json"
    movie_ids = set()
    if cache_file.exists():
        with open(cache_file, "r", encoding="utf-8") as f:
            cache = json.load(f)
        for key, val in cache.items():
            for name, _ in RETRY_MOVIES:
                if name in key:
                    movie_ids.add(str(val.get("id", "")))
                    break

    # 清除这些电影的进度
    removed = 0
    for mid in movie_ids:
        if mid in progress:
            del progress[mid]
            removed += 1

    # 也清除所有标记为 completed=False 但 scraped_ids 为空的条目
    to_remove = []
    for key, val in progress.items():
        if isinstance(val, dict) and val.get("total_scraped", 0) < 400:
            to_remove.append(key)
    for key in to_remove:
        del progress[key]
        removed += 1

    if removed > 0:
        with open(PROGRESS_FILE, "w", encoding="utf-8") as f:
            json.dump(progress, f, ensure_ascii=False, indent=2)
        print(f"  已清除 {removed} 条进度记录")
    else:
        print(f"  无需清除进度记录")


if __name__ == "__main__":
    print(f"将重采 {len(RETRY_MOVIES)} 部电影:")
    for n, y in RETRY_MOVIES:
        print(f"  - {n} ({y})")

    print("\n清除进度记录...")
    reset_progress()
    print()

    from scraper.douban_review import run_direct
    names = [m[0] for m in RETRY_MOVIES]
    years = [m[1] for m in RETRY_MOVIES]
    run_direct(movies=names, years=years)
