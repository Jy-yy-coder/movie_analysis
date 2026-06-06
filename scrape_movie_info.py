"""
豆瓣电影详细信息采集脚本
========================
采集内容：片名、年份、导演、编剧、主演、类型、制片国家/地区、
          语言、上映日期、片长、海报、豆瓣评分、剧情简介
"""

import json
import random
import re
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

sys.path.insert(0, str(Path(__file__).resolve().parent))

from config import (
    DOUBAN_BASE_URL, RAW_DATA_DIR, BROWSER_DATA_DIR, MOVIE_CACHE_FILE,
)

OUTPUT_FILE = RAW_DATA_DIR / "movies_info.json"
POSTER_DIR = RAW_DATA_DIR / "posters"


def random_delay(min_s=2.0, max_s=5.0):
    time.sleep(random.uniform(min_s, max_s))


def start_browser():
    """启动浏览器（复用 cookies）"""
    pw = sync_playwright().start()

    try:
        context = pw.chromium.launch_persistent_context(
            user_data_dir=str(BROWSER_DATA_DIR),
            headless=False,
            viewport={"width": 1366, "height": 768},
            locale="zh-CN",
            args=["--disable-blink-features=AutomationControlled"],
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
        )
    except Exception:
        print("  ⚠ 持久化上下文失败，改用 cookies 模式...")
        browser = pw.chromium.launch(
            headless=False,
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
        )
        context = browser.new_context(
            viewport={"width": 1366, "height": 768},
            locale="zh-CN",
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
        )
        cookies_file = BROWSER_DATA_DIR / "douban_cookies.json"
        if cookies_file.exists():
            with open(cookies_file, "r", encoding="utf-8") as f:
                cookies = json.load(f)
            context.add_cookies(cookies)

    page = context.new_page()

    # 注入反检测
    stealth_js = """
    Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
    window.chrome = {runtime: {}};
    """
    page.add_init_script(stealth_js)

    return pw, context, page


def check_login(page):
    """检查登录状态"""
    page.goto("https://www.douban.com/", wait_until="domcontentloaded", timeout=15000)
    time.sleep(2)
    content = page.content()
    if "登录" in content and "nav-user-account" not in content:
        return False
    return True


def wait_for_login(page):
    """等待用户手动登录"""
    print("  ⚠  未检测到登录状态")
    print("      请在浏览器中手动完成登录操作")
    print("      登录成功后程序将自动继续...")
    for i in range(60):
        time.sleep(5)
        try:
            page.goto("https://www.douban.com/", wait_until="domcontentloaded", timeout=10000)
            time.sleep(1)
            if check_login(page):
                print("  ✓ 登录成功！")
                # 保存 cookies
                try:
                    cookies = page.context.cookies()
                    cookies_file = BROWSER_DATA_DIR / "douban_cookies.json"
                    BROWSER_DATA_DIR.mkdir(parents=True, exist_ok=True)
                    with open(cookies_file, "w", encoding="utf-8") as f:
                        json.dump(cookies, f, ensure_ascii=False, indent=2)
                except Exception:
                    pass
                return True
        except Exception:
            pass
    return False


def extract_info_label(page, label_text):
    """通过 label 文本提取 info 中的值"""
    try:
        result = page.evaluate(f"""
        () => {{
            const spans = document.querySelectorAll('#info span.pl');
            for (const span of spans) {{
                const text = span.textContent.trim();
                if (text.startsWith('{label_text}')) {{
                    // 获取 span 后面的内容
                    let parent = span.parentElement;
                    let next = span.nextSibling;
                    let values = [];
                    
                    // 有些值直接在后面的 text node 中
                    if (next && next.nodeType === 3) {{
                        values.push(next.textContent.trim().replace(/\\n/g, '').replace(/\\s+/g, ' ').replace(/ \\/ /g, ' / '));
                    }}
                    
                    // 有些值在后面的 <a> 或其他元素中
                    let sibling = span.nextElementSibling;
                    while (sibling) {{
                        const cls = sibling.getAttribute('class') || '';
                        if (cls.includes('pl')) break; // 下一个 label 了
                        const t = sibling.textContent.trim();
                        if (t && t !== '/' && t !== '\\n') {{
                            values.push(t.replace(/\\s+/g, ' '));
                        }}
                        sibling = sibling.nextElementSibling;
                    }}
                    
                    if (values.length > 0) {{
                        // 拼接所有值，用 / 分隔
                        let combined = '';
                        // 重新从 parent 获取所有内容
                        let html = parent.innerHTML;
                        // 找到 label 后面的内容
                        let labelIdx = html.indexOf('{label_text}');
                        if (labelIdx === -1) return values.join(' / ');
                        let afterLabel = html.substring(labelIdx);
                        // 去掉 label span 本身
                        let closeIdx = afterLabel.indexOf('</span>');
                        if (closeIdx === -1) return values.join(' / ');
                        let contentAfter = afterLabel.substring(closeIdx + 7);
                        // 取到下一个 <span class="pl"> 之前
                        let nextLabel = contentAfter.indexOf('<span class="pl">');
                        if (nextLabel > 0) contentAfter = contentAfter.substring(0, nextLabel);
                        // 清理 HTML 标签
                        contentAfter = contentAfter.replace(/<[^>]+>/g, '').replace(/&nbsp;/g, ' ').trim();
                        contentAfter = contentAfter.replace(/\\s+/g, ' ').replace(/\\s*\\/\\s*/g, ' / ');
                        return contentAfter;
                    }}
                    return '';
                }}
            }}
            return '';
        }}
        """)
        return result.strip() if result else ""
    except Exception:
        return ""


def extract_directors(page):
    """提取导演"""
    try:
        directors = page.evaluate("""
        () => {
            const links = document.querySelectorAll('#info a[rel="v:directedBy"]');
            return Array.from(links).map(a => a.textContent.trim()).join(' / ');
        }
        """)
        return directors.strip() if directors else ""
    except Exception:
        return ""


def extract_actors(page):
    """提取主演"""
    try:
        actors = page.evaluate("""
        () => {
            const links = document.querySelectorAll('#info a[rel="v:starring"]');
            return Array.from(links).map(a => a.textContent.trim()).join(' / ');
        }
        """)
        return actors.strip() if actors else ""
    except Exception:
        return ""


def extract_genres(page):
    """提取类型"""
    try:
        genres = page.evaluate("""
        () => {
            const spans = document.querySelectorAll('#info span[property="v:genre"]');
            return Array.from(spans).map(s => s.textContent.trim()).join(' / ');
        }
        """)
        return genres.strip() if genres else ""
    except Exception:
        return ""


def extract_runtime(page):
    """提取片长"""
    try:
        runtime = page.evaluate("""
        () => {
            const spans = document.querySelectorAll('#info span[property="v:runtime"]');
            return Array.from(spans).map(s => s.textContent.trim()).join(' / ');
        }
        """)
        return runtime.strip() if runtime else ""
    except Exception:
        return ""


def extract_release_date(page):
    """提取上映日期"""
    try:
        dates = page.evaluate("""
        () => {
            const spans = document.querySelectorAll('#info span[property="v:initialReleaseDate"]');
            return Array.from(spans).map(s => s.textContent.trim()).join(' / ');
        }
        """)
        return dates.strip() if dates else ""
    except Exception:
        return ""


def extract_rating(page):
    """提取豆瓣评分"""
    try:
        rating = page.evaluate("""
        () => {
            const el = document.querySelector('strong.ll.rating_num');
            return el ? el.textContent.trim() : '';
        }
        """)
        return rating.strip() if rating else ""
    except Exception:
        return ""


def extract_summary(page):
    """提取剧情简介"""
    try:
        summary = page.evaluate("""
        () => {
            // 先尝试展开的简介
            const span = document.querySelector('span[property="v:summary"]');
            if (span) return span.textContent.trim();
            return '';
        }
        """)
        return summary.strip() if summary else ""
    except Exception:
        return ""


def extract_poster_url(page):
    """提取海报图片URL"""
    try:
        url = page.evaluate("""
        () => {
            const img = document.querySelector('#mainpic img');
            return img ? img.getAttribute('src') : '';
        }
        """)
        return url.strip() if url else ""
    except Exception:
        return ""


def download_poster(page, url, save_path):
    """下载海报图片"""
    try:
        resp = page.request.get(url)
        if resp.ok:
            save_path.parent.mkdir(parents=True, exist_ok=True)
            with open(save_path, "wb") as f:
                f.write(resp.body())
            return True
    except Exception as e:
        print(f"    ⚠ 海报下载失败: {e}")
    return False


def scrape_movie_info(page, movie_id, movie_title):
    """采集单部电影的详细信息"""
    url = f"https://movie.douban.com/subject/{movie_id}/"
    print(f"\n  🎬 采集: {movie_title} (ID: {movie_id})")

    try:
        page.goto(url, wait_until="domcontentloaded", timeout=20000)
    except PlaywrightTimeout:
        print(f"    ⚠ 页面加载超时")
        return None
    except Exception as e:
        print(f"    ⚠ 页面加载失败: {e}")
        return None

    time.sleep(1.5)

    info = {
        "movie_id": movie_id,
        "片名": movie_title,
        "年份": "",
        "导演": extract_directors(page),
        "编剧": extract_info_label(page, "编剧"),
        "主演": extract_actors(page),
        "类型": extract_genres(page),
        "制片国家/地区": extract_info_label(page, "制片国家"),
        "语言": extract_info_label(page, "语言"),
        "上映日期": extract_release_date(page),
        "片长": extract_runtime(page),
        "海报URL": "",
        "海报本地路径": "",
        "豆瓣评分": extract_rating(page),
        "剧情简介": extract_summary(page),
    }

    # 年份 - 从页面 title 或上映日期提取
    try:
        year_text = page.evaluate("""
        () => {
            const el = document.querySelector('.year');
            if (el) return el.textContent.replace(/[()（）]/g, '').trim();
            return '';
        }
        """)
        info["年份"] = year_text.strip() if year_text else ""
    except Exception:
        pass

    # 海报
    poster_url = extract_poster_url(page)
    info["海报URL"] = poster_url
    if poster_url:
        safe_name = re.sub(r'[\\/:*?"<>|]', '', movie_title)
        poster_path = POSTER_DIR / f"{safe_name}.jpg"
        if download_poster(page, poster_url, poster_path):
            info["海报本地路径"] = str(poster_path)
            print(f"    ✓ 海报已保存")
        else:
            print(f"    ⚠ 海报下载失败")

    # 打印摘要
    print(f"    评分: {info['豆瓣评分']} | 导演: {info['导演']} | 类型: {info['类型']}")

    return info


def main():
    # 加载缓存
    with open(MOVIE_CACHE_FILE, "r", encoding="utf-8") as f:
        cache = json.load(f)

    # 加载已有结果（支持断点续采）
    existing = {}
    if OUTPUT_FILE.exists():
        with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
            existing = json.load(f)
        print(f"  已有 {len(existing)} 部电影信息")

    movies = list(cache.items())
    total = len(movies)
    print(f"  共 {total} 部电影待采集\n")

    # 启动浏览器
    pw, context, page = start_browser()
    print("  ✓ 浏览器启动成功")

    # 检查登录
    if not check_login(page):
        if not wait_for_login(page):
            print("  ✗ 登录超时")
            context.close()
            pw.stop()
            return

    # 逐部采集
    success = 0
    fail = 0
    for i, (key, val) in enumerate(movies, 1):
        movie_id = val["movie_id"]
        title = val["title"]

        # 跳过已采集的
        if movie_id in existing:
            print(f"  [{i}/{total}] ⏭ 跳过已采集: {title}")
            continue

        print(f"  [{i}/{total}]", end="")

        info = scrape_movie_info(page, movie_id, title)
        if info:
            existing[movie_id] = info
            success += 1
            # 每部采集后立即保存
            with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
                json.dump(existing, f, ensure_ascii=False, indent=2)
        else:
            fail += 1

        random_delay(2.0, 4.0)

    # 保存最终结果
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(existing, f, ensure_ascii=False, indent=2)

    print(f"\n{'=' * 60}")
    print(f"  🎉 采集完成！成功: {success} | 失败: {fail}")
    print(f"  📁 保存至: {OUTPUT_FILE}")
    print(f"  🖼 海报目录: {POSTER_DIR}")
    print(f"{'=' * 60}")

    context.close()
    pw.stop()


if __name__ == "__main__":
    main()
