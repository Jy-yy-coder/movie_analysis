import sys
import os

# 获取项目根目录
root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 将项目根目录加入路径
sys.path.insert(0, root_dir)

# 切换工作目录到项目根目录，确保相对路径正确
os.chdir(root_dir)

from app import app

# Vercel 需要的 WSGI 入口
application = app
