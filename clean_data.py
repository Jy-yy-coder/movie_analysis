"""
数据清洗脚本
1. 去除重复评论
2. 去除空评论
3. 标准化评分字段
4. 统一时间格式
5. 清理评论内容（去多余空白、特殊字符）
6. 输出清洗报告
"""

import pandas as pd
import os
import glob
import re
import json

RAW_DIR = 'data/raw'
CLEAN_DIR = 'data/cleaned'
os.makedirs(CLEAN_DIR, exist_ok=True)

csvs = sorted(glob.glob(os.path.join(RAW_DIR, '*_comments.csv')))

report = []
total_before = 0
total_after = 0

print('=' * 80)
print('数据清洗开始')
print('=' * 80)

for f in csvs:
    name = os.path.basename(f).replace('_comments.csv', '')
    df = pd.read_csv(f)
    rows_before = len(df)
    total_before += rows_before

    changes = []

    # 1. 去除完全重复的行
    dup_count = df.duplicated().sum()
    if dup_count > 0:
        df = df.drop_duplicates()
        changes.append(f'去重复{dup_count}条')

    # 2. 去除评论ID重复
    if '评论ID' in df.columns:
        id_dup = df['评论ID'].duplicated().sum()
        if id_dup > 0:
            df = df.drop_duplicates(subset='评论ID', keep='first')
            changes.append(f'去ID重复{id_dup}条')

    # 3. 去除评论内容为空的行
    if '评论内容' in df.columns:
        null_count = df['评论内容'].isna().sum()
        if null_count > 0:
            df = df.dropna(subset=['评论内容'])
            changes.append(f'去空评论{null_count}条')

    # 4. 清理评论内容
    def clean_comment(text):
        if pd.isna(text):
            return text
        text = str(text)
        # 去除多余空白
        text = re.sub(r'\s+', ' ', text).strip()
        # 去除展开提示文字
        text = text.replace('(展开)', '').replace('（展开）', '').strip()
        return text

    if '评论内容' in df.columns:
        df['评论内容'] = df['评论内容'].apply(clean_comment)

    # 5. 清理评论中过短的（少于2个字的没分析价值）
    if '评论内容' in df.columns:
        short_count = (df['评论内容'].str.len() < 2).sum()
        if short_count > 0:
            df = df[df['评论内容'].str.len() >= 2]
            changes.append(f'去过短评论{short_count}条')

    # 6. 标准化评分（确保是数值）
    if '用户评分' in df.columns:
        df['用户评分'] = pd.to_numeric(df['用户评分'], errors='coerce')
        null_rating = df['用户评分'].isna().sum()
        if null_rating > 0:
            changes.append(f'评分缺失{null_rating}条（保留，后续分析可过滤）')

    # 7. 标准化时间
    if '评论时间' in df.columns:
        df['评论时间'] = pd.to_datetime(df['评论时间'], errors='coerce')

    # 8. 确保数据类型正确
    if '点赞数' in df.columns:
        df['点赞数'] = pd.to_numeric(df['点赞数'], errors='coerce').fillna(0).astype(int)
    if '上映年份' in df.columns:
        df['上映年份'] = df['上映年份'].astype(int)

    # 9. 重置索引
    df = df.reset_index(drop=True)

    rows_after = len(df)
    total_after += rows_after
    removed = rows_before - rows_after

    # 保存清洗后的数据
    out_path = os.path.join(CLEAN_DIR, f'{name}_comments.csv')
    df.to_csv(out_path, index=False, encoding='utf-8-sig')

    change_str = ', '.join(changes) if changes else '无变化'
    status = 'OK' if removed == 0 else f'-{removed}条'
    print(f'{name:<24} {rows_before:>5} -> {rows_after:>5}  {status:>8}  ({change_str})')

    report.append({
        '电影': name,
        '原始条数': rows_before,
        '清洗后条数': rows_after,
        '删除条数': removed,
        '操作': change_str
    })

print('=' * 80)
print(f'总计: {total_before} -> {total_after} (删除 {total_before - total_after} 条, 保留率 {total_after/total_before*100:.1f}%)')
print(f'清洗后数据保存在: {CLEAN_DIR}/')

# 保存清洗报告
with open(os.path.join(CLEAN_DIR, 'clean_report.json'), 'w', encoding='utf-8') as f:
    json.dump(report, f, ensure_ascii=False, indent=2)
print(f'清洗报告: {CLEAN_DIR}/clean_report.json')

# 同时清洗电影信息CSV
print('\n--- 清洗电影信息 ---')
info_df = pd.read_csv(os.path.join(RAW_DIR, 'movies_info.csv'))
print(f'电影信息: {len(info_df)} 条记录')

# 清洗编剧字段前缀
if '编剧' in info_df.columns:
    info_df['编剧'] = info_df['编剧'].apply(
        lambda x: x.lstrip(': ').strip() if isinstance(x, str) else x
    )

# 保存
info_df.to_csv(os.path.join(CLEAN_DIR, 'movies_info.csv'), index=False, encoding='utf-8-sig')
print('电影信息已清洗并保存')

print('\n全部清洗完成！数据可以用于分析了。')
