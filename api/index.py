import sys
import os

# 将项目根目录加入路径，以便导入 app
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app

# Vercel 需要的 WSGI 入口
application = app
