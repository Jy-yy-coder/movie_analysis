"""
豆瓣电影短评采集程序（增强版）
================================
功能特性：
  ✅ 自动搜索电影豆瓣页面，获取电影 ID
  ✅ 自动打开浏览器（Playwright 持久化上下文）
  ✅ 支持人工登录豆瓣，自动保存登录状态
  ✅ 下次运行无需重复登录
  ✅ 自动翻页采集评论（每部电影 ≥ 500 条）
  ✅ 自动处理异常与验证码
  ✅ 断点续爬（进度保存至 JSON）
  ✅ 自动去重（基于评论 ID）
  ✅ 搜索结果缓存（避免重复搜索）

运行方法：
  D:\\anaconda\\python.exe scraper\\douban_review.py
"""

import csv
import json
import random
import re
import sys
import time
import traceback
from pathlib import Path

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

# 将项目根目录加入 sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import (
    DOUBAN_BASE_URL,
    DOUBAN_LOGIN_URL,
    DOUBAN_SEARCH_URL,
    RAW_DATA_DIR,
    BROWSER_DATA_DIR,
    PROGRESS_FILE,
    MOVIE_CACHE_FILE,
    SPRING_FESTIVAL_MOVIES,
    CSV_FIELDNAMES,
    DELAY_MIN,
    DELAY_MAX,
    SEARCH_DELAY_MIN,
    SEARCH_DELAY_MAX,
    MAX_EMPTY_PAGES,
    COMMENTS_PER_PAGE,
    MIN_REVIEWS_PER_MOVIE,
)


# ======================== 工具函数 ========================

def sanitize_filename(name: str) -> str:
    """将电影名称转为安全的文件名"""
    return re.sub(r'[\\/:*?"<>|]', '', name).strip()


def random_delay(min_sec: float = DELAY_MIN, max_sec: float = DELAY_MAX):
    """随机延时，模拟人类浏览行为"""
    time.sleep(random.uniform(min_sec, max_sec))


def print_separator(char: str = "=", length: int = 60):
    """打印分隔线"""
    print(f"\n{char * length}")


# ======================== 核心爬虫类 ========================

class DoubanReviewScraper:
    """豆瓣电影短评采集器（自动搜索版）"""

    def __init__(self):
        self.playwright = None
        self.context = None
        self.page = None
        self.progress = self._load_progress()
        self.movie_cache = self._load_movie_cache()

    # ==================== 电影搜索缓存 ====================

    def _load_movie_cache(self) -> dict:
        """加载电影搜索结果缓存"""
        if MOVIE_CACHE_FILE.exists():
            try:
                with open(MOVIE_CACHE_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError):
                pass
        return {}

    def _save_movie_cache(self):
        """保存电影搜索缓存"""
        MOVIE_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(MOVIE_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(self.movie_cache, f, ensure_ascii=False, indent=2)

    # ==================== 进度管理 ====================

    def _load_progress(self) -> dict:
        """加载爬取进度（断点续爬）"""
        if PROGRESS_FILE.exists():
            try:
                with open(PROGRESS_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError):
                print("  ⚠ 进度文件损坏，将从头开始采集")
        return {}

    def _save_progress(self):
        """保存爬取进度到文件"""
        PROGRESS_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(PROGRESS_FILE, "w", encoding="utf-8") as f:
            json.dump(self.progress, f, ensure_ascii=False, indent=2)

    def _get_movie_progress(self, movie_id: str) -> dict:
        """获取某部电影的爬取进度"""
        return self.progress.get(movie_id, {
            "last_offset": 0,
            "scraped_ids": [],
            "total_scraped": 0,
            "completed": False,
        })

    def _update_movie_progress(self, movie_id: str, comment_id: str, offset: int):
        """更新爬取进度"""
        if movie_id not in self.progress:
            self.progress[movie_id] = {
                "last_offset": 0,
                "scraped_ids": [],
                "total_scraped": 0,
                "completed": False,
            }
        prog = self.progress[movie_id]
        if comment_id and comment_id not in prog["scraped_ids"]:
            prog["scraped_ids"].append(comment_id)
        prog["last_offset"] = offset
        prog["total_scraped"] = len(prog["scraped_ids"])
        self._save_progress()

    def _mark_movie_completed(self, movie_id: str):
        """标记某部电影采集完成"""
        if movie_id in self.progress:
            self.progress[movie_id]["completed"] = True
            self._save_progress()

    # ==================== 浏览器管理 ====================

    def start_browser(self):
        """启动浏览器（使用 cookies 文件保存登录态）"""
        print_separator()
        print("  豆瓣电影评论采集系统（自动搜索增强版）")
        print_separator()
        print("\n  [1/4] 正在启动浏览器...")

        self.playwright = sync_playwright().start()

        # 尝试 launch_persistent_context（保留旧方式兼容）
        try:
            self.context = self.playwright.chromium.launch_persistent_context(
                user_data_dir=str(BROWSER_DATA_DIR),
                headless=False,
                viewport={"width": 1366, "height": 768},
                locale="zh-CN",
                args=[
                    "--disable-blink-features=AutomationControlled",
                ],
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
            )
        except Exception:
            # 如果 persistent context 失败（如中文路径），改用 launch + cookies 文件
            print("  ⚠ 持久化上下文启动失败，改用 cookies 文件模式...")
            browser = self.playwright.chromium.launch(
                headless=False,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                ],
            )
            self.context = browser.new_context(
                viewport={"width": 1366, "height": 768},
                locale="zh-CN",
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
            )
            # 从旧目录复制 cookies
            cookies_file = BROWSER_DATA_DIR / "douban_cookies.json"
            if cookies_file.exists():
                import json as _json
                with open(cookies_file, "r", encoding="utf-8") as cf:
                    cookies = _json.load(cf)
                self.context.add_cookies(cookies)
                print("  ✓ 已加载保存的 cookies")
            self._browser = browser  # 保存引用以防被回收

        # 注入反检测脚本
        for pg in self.context.pages:
            self._inject_stealth(pg)

        if self.context.pages:
            self.page = self.context.pages[0]
        else:
            self.page = self.context.new_page()
            self._inject_stealth(self.page)

        print("  ✓ 浏览器启动成功")

    def _save_cookies(self):
        """保存 cookies 到文件（用于非 persistent context 模式）"""
        try:
            cookies = self.context.cookies()
            cookies_file = BROWSER_DATA_DIR / "douban_cookies.json"
            BROWSER_DATA_DIR.mkdir(parents=True, exist_ok=True)
            with open(cookies_file, "w", encoding="utf-8") as f:
                json.dump(cookies, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _inject_stealth(self, page):
        """注入反检测脚本"""
        stealth_js = """
        Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
        Object.defineProperty(navigator, 'languages', { get: () => ['zh-CN', 'zh', 'en'] });
        Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
        window.chrome = { runtime: {} };
        """
        try:
            page.add_init_script(stealth_js)
        except Exception:
            pass

    # ==================== 登录检测 ====================

    def check_login(self) -> bool:
        """检查是否已登录豆瓣"""
        print("\n  [2/4] 正在检查登录状态...")
        try:
            self.page.goto(DOUBAN_BASE_URL, wait_until="domcontentloaded", timeout=30000)
            time.sleep(3)
        except PlaywrightTimeout:
            print("  ⚠ 页面加载超时，尝试继续...")
            return False
        except Exception as e:
            print(f"  ⚠ 访问豆瓣失败: {e}")
            return False

        logged_in_selectors = [
            "a.nb-avatar",
            ".nav-user-account",
            "a[href*='/mine/']",
            ".user-info",
        ]
        for selector in logged_in_selectors:
            try:
                if self.page.locator(selector).count() > 0:
                    print("  ✓ 已登录豆瓣")
                    self._save_cookies()
                    return True
            except Exception:
                continue

        try:
            login_btn = self.page.locator('a[href*="login"]').first
            if login_btn.count() == 0:
                print("  ✓ 已登录豆瓣")
                self._save_cookies()
                return True
        except Exception:
            pass

        return False

    def wait_for_login(self):
        """等待用户手动完成登录"""
        print()
        print("  " + "-" * 56)
        print("  ⚠  未检测到登录状态")
        print("      请在浏览器中手动完成登录操作")
        print("      登录成功后程序将自动继续...")
        print("  " + "-" * 56)

        try:
            self.page.goto(DOUBAN_LOGIN_URL, wait_until="domcontentloaded", timeout=30000)
        except Exception:
            pass

        max_wait_seconds = 300
        poll_interval = 3
        waited = 0

        while waited < max_wait_seconds:
            time.sleep(poll_interval)
            waited += poll_interval

            current_url = self.page.url
            if "login" not in current_url and "passport" not in current_url:
                print("  ✓ 登录成功！")
                time.sleep(2)
                return

            for selector in ["a.nb-avatar", ".nav-user-account", "a[href*='/mine/']"]:
                try:
                    if self.page.locator(selector).count() > 0:
                        print("  ✓ 登录成功！")
                        time.sleep(2)
                        return
                except Exception:
                    continue

            if waited % 30 == 0:
                print(f"  ⏳ 等待登录中... ({waited}/{max_wait_seconds}s)")

        print("  ⚠ 等待登录超时，将尝试继续运行...")

    # ==================== 自动搜索电影 ====================

    def search_movie(self, movie_name: str, year: int) -> dict:
        """
        在豆瓣搜索电影，自动获取电影 ID 和基础信息

        Args:
            movie_name: 电影名称
            year: 上映年份（用于精确匹配）

        Returns:
            dict: {"movie_id": str, "title": str, "score": float, "url": str}
                  搜索失败返回 None
        """
        # 先查缓存
        cache_key = f"{movie_name}_{year}"
        if cache_key in self.movie_cache:
            cached = self.movie_cache[cache_key]
            print(f"  ✓ 命中缓存: ID={cached['movie_id']}, "
                  f"评分={cached.get('score', 'N/A')}")
            return cached

        print(f"  🔍 正在搜索: {movie_name} ({year})...")

        # 构造搜索关键词（带年份提高精度）
        search_query = f"{movie_name} {year}"

        # 方法1: 通过豆瓣搜索页
        movie_info = self._search_via_search_page(movie_name, year, search_query)

        if not movie_info:
            # 方法2: 通过 Google site 搜索
            movie_info = self._search_via_google(movie_name, year)

        if not movie_info:
            # 方法3: 直接尝试访问猜测URL
            movie_info = self._search_via_suggestion_api(movie_name, year)

        if movie_info:
            # 写入缓存
            self.movie_cache[cache_key] = movie_info
            self._save_movie_cache()
            print(f"  ✓ 找到: {movie_info['title']} "
                  f"(ID: {movie_info['movie_id']}, "
                  f"评分: {movie_info.get('score', 'N/A')})")
        else:
            print(f"  ✗ 未能自动找到: {movie_name}")

        return movie_info

    def _search_via_search_page(self, movie_name: str, year: int,
                                search_query: str) -> dict:
        """方法1: 豆瓣搜索页搜索"""
        try:
            search_url = f"{DOUBAN_SEARCH_URL}?search_text={search_query}&cat=1002"
            self.page.goto(search_url, wait_until="domcontentloaded", timeout=20000)
            time.sleep(random.uniform(SEARCH_DELAY_MIN, SEARCH_DELAY_MAX))

            # 检查是否被重定向到验证页
            if self._check_captcha_or_block():
                self._handle_captcha()

            # 豆瓣搜索结果列表（多种选择器兼容）
            result_selectors = [
                ".item-root a[href*='/subject/']",
                ".detail a[href*='/subject/']",
                ".result-list .result a[href*='/subject/']",
                "a[href*='/movie.douban.com/subject/']",
                "#content .item a[href*='/subject/']",
            ]

            for selector in result_selectors:
                try:
                    items = self.page.locator(selector).all()
                    for item in items[:5]:  # 只看前5个结果
                        href = item.get_attribute("href") or ""
                        # 提取电影 ID
                        id_match = re.search(r'/subject/(\d+)', href)
                        if not id_match:
                            continue

                        title_text = item.inner_text().strip()
                        # 简单匹配：搜索结果标题中包含电影名的关键词
                        name_keywords = re.sub(r'[：:·\s]', '', movie_name)
                        result_keywords = re.sub(r'[：:·\s]', '', title_text)

                        # 计算关键词重叠度
                        overlap = sum(
                            1 for kw in name_keywords
                            if kw in result_keywords
                        ) / max(len(name_keywords), 1)

                        if overlap > 0.4:  # 超过40%字符匹配
                            movie_id = id_match.group(1)
                            return self._fetch_movie_info(movie_id, year)
                except Exception:
                    continue

            # 如果选择器都不行，尝试从页面URL/内容中提取
            page_content = self.page.content()
            id_matches = re.findall(r'/subject/(\d{5,10})', page_content)
            for mid in set(id_matches[:5]):
                info = self._fetch_movie_info(mid, year)
                if info and self._is_movie_match(info, movie_name, year):
                    return info

        except PlaywrightTimeout:
            print("  ⚠ 搜索页加载超时")
        except Exception as e:
            print(f"  ⚠ 搜索页搜索异常: {e}")

        return None

    def _search_via_google(self, movie_name: str, year: int) -> dict:
        """方法2: 通过 Google site 搜索豆瓣"""
        try:
            query = f"site:movie.douban.com {movie_name} {year}"
            google_url = f"https://www.google.com/search?q={query}"
            self.page.goto(google_url, wait_until="domcontentloaded", timeout=15000)
            time.sleep(random.uniform(2, 4))

            # 从 Google 结果中提取豆瓣链接
            links = self.page.locator("a[href*='movie.douban.com/subject/']").all()
            for link in links[:3]:
                href = link.get_attribute("href") or ""
                id_match = re.search(r'/subject/(\d+)', href)
                if id_match:
                    movie_id = id_match.group(1)
                    info = self._fetch_movie_info(movie_id, year)
                    if info and self._is_movie_match(info, movie_name, year):
                        return info

        except Exception:
            pass

        try:
            # 尝试 Bing
            query = f"site:movie.douban.com {movie_name} {year}"
            bing_url = f"https://www.bing.com/search?q={query}"
            self.page.goto(bing_url, wait_until="domcontentloaded", timeout=15000)
            time.sleep(random.uniform(2, 4))

            page_text = self.page.content()
            id_matches = re.findall(r'movie\.douban\.com/subject/(\d{5,10})', page_text)
            for mid in set(id_matches[:3]):
                info = self._fetch_movie_info(mid, year)
                if info and self._is_movie_match(info, movie_name, year):
                    return info

        except Exception:
            pass

        return None

    def _search_via_suggestion_api(self, movie_name: str, year: int) -> dict:
        """方法3: 通过豆瓣建议/提示 API"""
        try:
            # 豆瓣搜索建议 API
            from urllib.parse import quote
            api_url = (
                f"https://movie.douban.com/j/subject_suggest?"
                f"q={quote(movie_name)}&_={int(time.time() * 1000)}"
            )

            # 用 page 直接请求 JSON
            resp = self.page.request.get(api_url)
            if resp.ok:
                data = resp.json()
                for item in data:
                    if item.get("type") == "movie":
                        movie_id = str(item.get("id", ""))
                        title = item.get("title", "")
                        # 检查年份匹配
                        item_year = item.get("year", "")
                        if movie_id and (not item_year or str(year) in str(item_year)):
                            return {
                                "movie_id": movie_id,
                                "title": title or movie_name,
                                "year": year,
                                "score": item.get("rate", ""),
                                "url": f"{DOUBAN_BASE_URL}/subject/{movie_id}/",
                            }
        except Exception:
            pass

        return None

    def _fetch_movie_info(self, movie_id: str, year: int) -> dict:
        """访问电影详情页获取基础信息"""
        try:
            url = f"{DOUBAN_BASE_URL}/subject/{movie_id}/"
            self.page.goto(url, wait_until="domcontentloaded", timeout=20000)
            time.sleep(random.uniform(1.5, 3))

            # 检查是否404
            page_text = self.page.inner_text("body") if self.page.locator("body").count() > 0 else ""
            if "页面不存在" in page_text or "404" in page_text:
                return None

            # 提取标题
            title = ""
            try:
                title_el = self.page.locator("#content h1 span").first
                title = title_el.inner_text().strip()
            except Exception:
                pass

            # 提取评分
            score = ""
            try:
                score_el = self.page.locator("strong.ll.rating_num").first
                score = score_el.inner_text().strip()
            except Exception:
                try:
                    score_el = self.page.locator(".rating_num").first
                    score = score_el.inner_text().strip()
                except Exception:
                    pass

            # 提取年份
            release_year = ""
            try:
                info_el = self.page.locator("#info").first
                info_text = info_el.inner_text()
                year_match = re.search(r'(\d{4})[-/]\d{2}[-/]\d{2}', info_text)
                if year_match:
                    release_year = year_match.group(1)
            except Exception:
                pass

            return {
                "movie_id": movie_id,
                "title": title,
                "year": int(release_year) if release_year.isdigit() else year,
                "score": score,
                "url": url,
            }
        except Exception:
            return None

    def _is_movie_match(self, info: dict, movie_name: str, year: int) -> bool:
        """检查搜索结果是否与目标电影匹配"""
        if not info:
            return False
        # 年份必须匹配（允许±1年误差）
        info_year = info.get("year", 0)
        if isinstance(info_year, (int, float)) and abs(info_year - year) > 1:
            return False
        # 名称匹配（去掉特殊字符后比较）
        name1 = re.sub(r'[：:·\s\-（）()]', '', movie_name)
        name2 = re.sub(r'[：:·\s\-（）()]', '', info.get("title", ""))
        if name1 in name2 or name2 in name1:
            return True
        # 计算字符重叠度
        overlap = sum(1 for c in name1 if c in name2) / max(len(name1), 1)
        return overlap > 0.5

    # ==================== 数据提取 ====================

    def _parse_rating(self, rating_element) -> int:
        """解析星级评分"""
        title_map = {"很差": 1, "较差": 2, "还行": 3, "推荐": 4, "力荐": 5}
        try:
            title = rating_element.get_attribute("title") or ""
            if title in title_map:
                return title_map[title]
        except Exception:
            pass

        try:
            cls = rating_element.get_attribute("class") or ""
            match = re.search(r"allstar(\d)0", cls)
            if match:
                return int(match.group(1))
        except Exception:
            pass

        return 0

    def _extract_reviews_from_page(self) -> list:
        """从当前页面提取所有评论数据"""
        reviews = []

        try:
            self.page.wait_for_selector(".comment-item", timeout=15000)
        except PlaywrightTimeout:
            print("  ⚠ 页面未加载到评论内容（可能被限制访问）")
            return reviews

        self._human_scroll()

        comment_items = self.page.locator(".comment-item").all()

        for item in comment_items:
            try:
                review = {}

                # 评论 ID
                cid = item.get_attribute("data-cid") or ""
                review["comment_id"] = cid

                # 用户昵称
                try:
                    user_link = item.locator(".comment-info a").first
                    review["user_name"] = user_link.inner_text().strip()
                except Exception:
                    review["user_name"] = ""

                # 用户评分
                try:
                    rating_el = item.locator(
                        ".comment-info span[class*='allstar']"
                    ).first
                    review["user_rating"] = self._parse_rating(rating_el)
                except Exception:
                    review["user_rating"] = 0

                # 评论时间
                try:
                    time_el = item.locator(".comment-info .comment-time").first
                    review["review_time"] = (
                        time_el.get_attribute("title") or time_el.inner_text()
                    ).strip()
                except Exception:
                    review["review_time"] = ""

                # 评论内容
                try:
                    short_el = item.locator(".short").first
                    review["content"] = short_el.inner_text().strip()
                except Exception:
                    review["content"] = ""

                # 点赞数
                try:
                    try:
                        votes_el = item.locator(".votes.vote-count").first
                        votes_text = votes_el.inner_text().strip()
                    except Exception:
                        votes_el = item.locator(".votes").first
                        votes_text = votes_el.inner_text().strip()
                    review["likes"] = int(votes_text) if votes_text.isdigit() else 0
                except Exception:
                    review["likes"] = 0

                if review["content"]:
                    reviews.append(review)

            except Exception:
                continue

        return reviews

    def _human_scroll(self):
        """模拟人类滚动页面行为"""
        try:
            total_height = self.page.evaluate("document.body.scrollHeight")
            current = 0
            while current < total_height:
                scroll_step = random.randint(200, 500)
                current = min(current + scroll_step, total_height)
                self.page.evaluate(f"window.scrollTo(0, {current})")
                time.sleep(random.uniform(0.2, 0.6))
                total_height = self.page.evaluate("document.body.scrollHeight")
        except Exception:
            pass

    # ==================== 异常处理 ====================

    def _check_captcha_or_block(self) -> bool:
        """检测是否出现验证码/封禁页面"""
        indicators = [
            "text=验证码",
            "text=请输入验证码",
            "#captcha_image",
            ".captcha",
            "text=检测到异常",
            "text=请求过于频繁",
            "text=访问受限",
        ]
        for indicator in indicators:
            try:
                if self.page.locator(indicator).count() > 0:
                    return True
            except Exception:
                continue
        if "sec.douban.com" in self.page.url or "blocked" in self.page.url.lower():
            return True
        return False

    def _handle_captcha(self):
        """处理验证码：暂停等待用户手动解决"""
        print()
        print("  " + "!" * 56)
        print("  ⚠  检测到验证码 / 反爬页面！")
        print("      请在浏览器中手动完成验证")
        print("      验证完成后程序将自动继续...")
        print("  " + "!" * 56)

        max_wait = 180
        waited = 0
        while waited < max_wait:
            time.sleep(3)
            waited += 3
            if not self._check_captcha_or_block():
                print("  ✓ 验证已通过，继续采集...")
                return

        print("  ⚠ 验证等待超时")

    # ==================== 翻页控制 ====================

    def _has_next_page(self) -> bool:
        """检查是否存在下一页"""
        try:
            next_link = self.page.locator("a.next")
            return next_link.count() > 0
        except Exception:
            return False

    def _goto_next_page(self) -> bool:
        """点击下一页"""
        max_retries = 3
        for attempt in range(1, max_retries + 1):
            try:
                next_link = self.page.locator("a.next").first
                if next_link.is_visible():
                    next_link.click()
                    random_delay(3, 6)
                    return True
            except Exception as e:
                print(f"  ⚠ 翻页失败 (尝试 {attempt}/{max_retries}): {e}")
                if attempt < max_retries:
                    time.sleep(3)
        return False

    # ==================== CSV 写入 ====================

    def _save_to_csv(self, reviews: list, movie_name: str, year: int,
                     csv_path: Path):
        """将评论追加写入 CSV"""
        file_exists = csv_path.exists() and csv_path.stat().st_size > 0

        with open(csv_path, "a", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=CSV_FIELDNAMES)

            if not file_exists:
                writer.writeheader()

            for review in reviews:
                writer.writerow({
                    "评论ID":   review.get("comment_id", ""),
                    "电影名称": movie_name,
                    "上映年份": year,
                    "用户昵称": review.get("user_name", ""),
                    "用户评分": review.get("user_rating", 0),
                    "评论内容": review.get("content", ""),
                    "评论时间": review.get("review_time", ""),
                    "点赞数":   review.get("likes", 0),
                })

    def _load_existing_ids(self, csv_path: Path) -> set:
        """从已有 CSV 中加载已采集的评论 ID"""
        existing_ids = set()
        if csv_path.exists():
            try:
                with open(csv_path, "r", encoding="utf-8-sig") as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        cid = row.get("评论ID", "").strip()
                        if cid:
                            existing_ids.add(cid)
            except Exception:
                pass
        return existing_ids

    def _count_existing_reviews(self, csv_path: Path) -> int:
        """统计 CSV 中已有评论数"""
        count = 0
        if csv_path.exists():
            try:
                with open(csv_path, "r", encoding="utf-8-sig") as f:
                    reader = csv.DictReader(f)
                    count = sum(1 for _ in reader)
            except Exception:
                pass
        return count

    # ==================== 单部电影采集 ====================

    def scrape_movie(self, movie_name: str, year: int, movie_id: str,
                     min_reviews: int = MIN_REVIEWS_PER_MOVIE):
        """
        采集某部电影的短评

        Args:
            movie_name:  电影名称
            year:        上映年份
            movie_id:    豆瓣电影 ID
            min_reviews: 最少采集评论数
        """
        print_separator()
        print(f"  🎬 开始采集: {movie_name} ({year}) ID:{movie_id}")
        print(f"     目标: 至少 {min_reviews} 条评论")
        print_separator()

        # 准备 CSV 路径
        safe_name = sanitize_filename(movie_name)
        csv_path = RAW_DATA_DIR / f"{safe_name}_comments.csv"

        # 已有数据量
        existing_count = self._count_existing_reviews(csv_path)
        existing_ids = self._load_existing_ids(csv_path)
        if existing_ids:
            print(f"  📂 已有 {existing_count} 条记录，将自动去重")

        # 已达标则跳过
        if existing_count >= min_reviews:
            print(f"  ✅ 已有 {existing_count} 条 ≥ {min_reviews} 条，跳过")
            self._mark_movie_completed(movie_id)
            return

        # 检查断点
        prog = self._get_movie_progress(movie_id)
        start_offset = prog.get("last_offset", 0)

        if prog.get("completed"):
            print("  ✅ 该电影已采集完成，跳过")
            return

        if start_offset > 0 and prog.get("scraped_ids"):
            print(f"  🔄 断点续爬：从第 {start_offset // COMMENTS_PER_PAGE + 1} 页继续")

        # 构建起始 URL
        if start_offset > 0:
            url = (
                f"{DOUBAN_BASE_URL}/subject/{movie_id}/comments"
                f"?start={start_offset}&limit={COMMENTS_PER_PAGE}"
                f"&sort=new_score&status=P"
            )
        else:
            url = f"{DOUBAN_BASE_URL}/subject/{movie_id}/comments"

        # 打开页面
        try:
            self.page.goto(url, wait_until="domcontentloaded", timeout=30000)
            random_delay(2, 4)
        except PlaywrightTimeout:
            print("  ⚠ 页面加载超时，跳过该电影")
            return
        except Exception as e:
            print(f"  ⚠ 页面访问失败: {e}")
            return

        # 检查页面是否存在
        for indicator in ["text=页面不存在", "text=条目不存在"]:
            try:
                if self.page.locator(indicator).count() > 0:
                    print(f"  ⚠ 页面不存在（ID: {movie_id}）")
                    return
            except Exception:
                continue

        # 开始逐页采集
        page_num = start_offset // COMMENTS_PER_PAGE + 1
        total_new = 0
        consecutive_empty = 0
        need_more = min_reviews - existing_count

        while True:
            # 达到目标数量
            if total_new >= need_more:
                print(f"\n  ✅ 已达目标数量 ({total_new} 条新增 ≥ {need_more} 条需补)")
                break

            print(f"\n  📄 第 {page_num} 页 | 已新增 {total_new}/{need_more} 条")

            # 检测验证码
            if self._check_captcha_or_block():
                self._handle_captcha()

            # 提取评论
            try:
                reviews = self._extract_reviews_from_page()
            except Exception as e:
                print(f"  ⚠ 提取失败: {e}")
                consecutive_empty += 1
                if consecutive_empty >= MAX_EMPTY_PAGES:
                    print(f"  ⚠ 连续 {MAX_EMPTY_PAGES} 次失败，停止")
                    break
                continue

            if not reviews:
                consecutive_empty += 1
                print(f"  ⚠ 本页无评论 ({consecutive_empty}/{MAX_EMPTY_PAGES})")
                if consecutive_empty >= MAX_EMPTY_PAGES:
                    print("  ✅ 已采集所有可访问评论")
                    break
            else:
                consecutive_empty = 0

                # 去重
                new_reviews = [
                    r for r in reviews
                    if r.get("comment_id") and r["comment_id"] not in existing_ids
                ]

                if new_reviews:
                    self._save_to_csv(new_reviews, movie_name, year, csv_path)
                    for r in new_reviews:
                        existing_ids.add(r["comment_id"])
                    total_new += len(new_reviews)
                    print(
                        f"  ✅ 本页 {len(reviews)} 条，"
                        f"新增 {len(new_reviews)} 条 "
                        f"(总新增: {total_new})"
                    )
                else:
                    print(f"  ⏭ 本页 {len(reviews)} 条均为重复，跳过")

            # 更新进度
            current_offset = (page_num - 1) * COMMENTS_PER_PAGE
            for r in reviews:
                rid = r.get("comment_id", "")
                if rid:
                    self._update_movie_progress(movie_id, rid, current_offset)

            # 翻页
            if not self._has_next_page():
                print("\n  ✅ 已到最后一页")
                self._mark_movie_completed(movie_id)
                break

            if not self._goto_next_page():
                print("\n  ⚠ 无法翻到下一页，停止采集")
                break

            page_num += 1
            random_delay()

        # 汇总
        final_count = self._count_existing_reviews(csv_path)
        print(f"\n  📊 {movie_name} ({year}) 采集结束")
        print(f"     本次新增: {total_new} 条")
        print(f"     文件总计: {final_count} 条")
        print(f"     保存路径: {csv_path}")

        if final_count >= min_reviews:
            self._mark_movie_completed(movie_id)

    # ==================== 主运行入口 ====================

    def run(self, movie_names: list = None, years: list = None,
            min_reviews: int = MIN_REVIEWS_PER_MOVIE):
        """
        运行采集主流程

        Args:
            movie_names: 指定电影名称列表（None=全部）
            years:       指定年份列表（None=全部年份）
            min_reviews: 每部电影最少采集数
        """
        try:
            # 1. 启动浏览器
            self.start_browser()

            # 2. 登录检查
            if not self.check_login():
                self.wait_for_login()

            # 3. 构建采集任务列表
            print("\n  [3/4] 正在搜索电影信息...\n")

            tasks = []  # [(movie_name, year, movie_id), ...]

            for year, movie_list in sorted(SPRING_FESTIVAL_MOVIES.items()):
                if years and year not in years:
                    continue
                for name in movie_list:
                    if movie_names and name not in movie_names:
                        continue
                    tasks.append((name, year))

            if not tasks:
                print("  ⚠ 没有匹配的采集任务")
                return

            print(f"  共 {len(tasks)} 部电影待采集\n")

            # 4. 逐部搜索并采集
            success_count = 0
            fail_count = 0
            total_tasks = len(tasks)

            for idx, (name, year) in enumerate(tasks, 1):
                print(f"\n  {'=' * 56}")
                print(f"  ▶ 总进度: [{idx}/{total_tasks}] "
                      f"成功: {success_count} | 失败: {fail_count}")
                print(f"  {'=' * 56}")

                # 4.1 搜索电影
                movie_info = self.search_movie(name, year)

                if not movie_info:
                    print(f"  ✗ 跳过: {name} ({year}) - 未找到豆瓣页面")
                    fail_count += 1
                    continue

                movie_id = movie_info["movie_id"]

                # 4.2 采集评论
                try:
                    self.scrape_movie(name, year, movie_id,
                                      min_reviews=min_reviews)
                    success_count += 1
                except Exception as e:
                    print(f"  ✗ 采集异常: {name} - {e}")
                    fail_count += 1
                    traceback.print_exc()

                # 电影间额外延时
                if idx < total_tasks:
                    extra_delay = random.uniform(5, 10)
                    print(f"\n  ⏳ 等待 {extra_delay:.1f}s 后继续下一部...")
                    time.sleep(extra_delay)

            # 5. 完成汇总
            print_separator("*")
            print("  🎉 所有采集任务已完成！")
            print(f"  📊 总计: {total_tasks} 部 | "
                  f"成功: {success_count} | 失败: {fail_count}")
            print(f"  📁 数据目录: {RAW_DATA_DIR}")

            # 列出已生成的 CSV 文件
            csv_files = list(RAW_DATA_DIR.glob("*_comments.csv"))
            if csv_files:
                print(f"\n  📋 已生成文件:")
                for f in sorted(csv_files):
                    lines = sum(1 for _ in open(f, "r", encoding="utf-8-sig")) - 1
                    print(f"     {f.name} ({lines} 条)")

            print_separator("*")

        except KeyboardInterrupt:
            print("\n\n  ⚠ 用户中断采集，进度已保存")
            print("  💡 下次运行将从断点继续")
        except Exception as e:
            print(f"\n  ❌ 程序异常: {e}")
            traceback.print_exc()
        finally:
            self.close()

    def close(self):
        """安全关闭浏览器，保存进度"""
        try:
            self._save_progress()
            self._save_movie_cache()
        except Exception:
            pass
        try:
            if self.context:
                self.context.close()
        except Exception:
            pass
        try:
            if self.playwright:
                self.playwright.stop()
        except Exception:
            pass
        print("  ✓ 浏览器已关闭，进度已保存")


# ======================== 交互式菜单 ========================

def show_menu():
    """显示交互式选择菜单"""
    print_separator()
    print("  《2021-2026年春节档电影口碑分析》评论数据采集")
    print_separator()

    all_movies = []
    for year, movie_list in sorted(SPRING_FESTIVAL_MOVIES.items()):
        print(f"\n  ---- {year}年春节档 ----")
        for name in movie_list:
            idx = len(all_movies) + 1
            print(f"    {idx:2d}. {name}")
            all_movies.append((name, year))

    total = len(all_movies)
    print(f"\n    {total + 1:2d}. 全部采集")
    print(f"     0. 退出程序")

    print()
    choice = input("  请输入编号（多个用逗号分隔，如 1,3,7）: ").strip()
    if choice == "0":
        print("  再见！")
        sys.exit(0)

    min_reviews_input = input(
        f"  每部电影最少采集条数（回车=默认{MIN_REVIEWS_PER_MOVIE}条）: "
    ).strip()
    min_reviews = (int(min_reviews_input)
                   if min_reviews_input.isdigit() else MIN_REVIEWS_PER_MOVIE)

    if choice == str(total + 1):
        return None, None, min_reviews

    selected_names = []
    selected_years = []
    for c in choice.split(","):
        c = c.strip()
        if c.isdigit():
            i = int(c) - 1
            if 0 <= i < total:
                selected_names.append(all_movies[i][0])
                selected_years.append(all_movies[i][1])

    return (selected_names if selected_names else None), \
           (selected_years if selected_years else None), \
           min_reviews


# ======================== 程序入口 ========================

def run_direct(movies=None, years=None, min_reviews=None):
    """直接运行（无需交互式菜单，供外部调用）"""
    scraper = DoubanReviewScraper()
    scraper.run(
        movie_names=movies,
        years=years,
        min_reviews=min_reviews or MIN_REVIEWS_PER_MOVIE,
    )


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="豆瓣电影短评采集程序"
    )
    parser.add_argument(
        "--all", action="store_true",
        help="采集全部电影（跳过交互菜单）"
    )
    parser.add_argument(
        "--min", type=int, default=None,
        help=f"每部电影最少采集条数（默认 {MIN_REVIEWS_PER_MOVIE}）"
    )
    args = parser.parse_args()

    if args.all:
        # 直接全部采集，无需交互
        scraper = DoubanReviewScraper()
        scraper.run(
            movie_names=None,
            years=None,
            min_reviews=args.min or MIN_REVIEWS_PER_MOVIE,
        )
    else:
        # 交互式菜单
        selected_movies, selected_years, min_reviews = show_menu()
        scraper = DoubanReviewScraper()
        scraper.run(
            movie_names=selected_movies,
            years=selected_years,
            min_reviews=min_reviews,
        )
