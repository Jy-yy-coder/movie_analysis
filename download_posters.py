"""
批量下载所有电影海报图片
使用 requests + 伪造 Referer 绕过豆瓣防盗链
"""

import json
import os
import time
import requests

POSTERS_DIR = os.path.join(os.path.dirname(__file__), 'data', 'raw', 'posters')
INFO_FILE = os.path.join(os.path.dirname(__file__), 'data', 'raw', 'movies_info.json')

os.makedirs(POSTERS_DIR, exist_ok=True)

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36',
    'Referer': 'https://movie.douban.com/',
    'Accept': 'image/webp,image/apng,image/*,*/*;q=0.8',
}

def download_posters():
    with open(INFO_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f)

    total = len(data)
    success = 0
    skip = 0
    fail = 0

    for i, (mid, info) in enumerate(data.items(), 1):
        title = info.get('片名', mid)
        url = info.get('海报URL', '')

        # 检查是否已有海报
        poster_path = os.path.join(POSTERS_DIR, f'{title}.jpg')
        if os.path.exists(poster_path) and os.path.getsize(poster_path) > 5000:
            print(f'[{i}/{total}] 跳过 {title}（已存在）')
            skip += 1
            continue

        if not url:
            print(f'[{i}/{total}] 无URL: {title}')
            fail += 1
            continue

        print(f'[{i}/{total}] 下载 {title} ...', end=' ')
        try:
            resp = requests.get(url, headers=HEADERS, timeout=30)
            if resp.status_code == 200 and len(resp.content) > 5000:
                with open(poster_path, 'wb') as f:
                    f.write(resp.content)
                size_kb = len(resp.content) / 1024
                print(f'成功 ({size_kb:.1f}KB)')
                success += 1
            else:
                print(f'失败 (HTTP {resp.status_code}, {len(resp.content)} bytes)')
                fail += 1
        except Exception as e:
            print(f'异常: {e}')
            fail += 1

        time.sleep(0.5)

    print(f'\n完成！成功: {success}, 跳过: {skip}, 失败: {fail}')


if __name__ == '__main__':
    download_posters()
