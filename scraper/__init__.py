"""
数据采集模块
============
提供豆瓣电影评论采集功能（自动搜索增强版）
"""

from .douban_review import DoubanReviewScraper

__all__ = ["DoubanReviewScraper"]
