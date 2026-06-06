import pandas as pd
import os

# 使用基于脚本位置的相对路径
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
output_dir = os.path.join(BASE_DIR, 'output')
files = ['trend_analysis.csv', 'sentiment_analysis.csv', 'lda_topic_summary.csv', '高频词统计.csv', '口碑对比分析.csv']

for f in files:
    filepath = os.path.join(output_dir, f)
    if os.path.exists(filepath):
        df = pd.read_csv(filepath, encoding='utf-8-sig')
        print(f'{f}:')
        print(f'  列名: {list(df.columns)}')
        print(f'  前2行数据:')
        print(df.head(2).to_dict('records'))
        print()
    else:
        print(f'{f}: 不存在')
        print()
