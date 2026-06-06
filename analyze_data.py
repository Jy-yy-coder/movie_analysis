"""
春节档电影口碑变化与负面评价成因可视化分析
============================================
1. 豆瓣评分趋势分析
2. 年度平均评分分析
3. 情感分析（SnowNLP）
4. 负面评论识别
5. 高频词统计（jieba）
6. LDA主题分析
7. 高口碑与低口碑电影对比
输出CSV + 可视化图表
"""

import pandas as pd
import numpy as np
import os
import glob
import re
import json
import warnings
from collections import Counter

import jieba
import jieba.analyse
from snownlp import SnowNLP
from wordcloud import WordCloud
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.decomposition import LatentDirichletAllocation

warnings.filterwarnings('ignore')

# ============ 路径配置 ============
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CLEAN_DIR = os.path.join(BASE_DIR, 'data', 'cleaned')
OUTPUT_DIR = os.path.join(BASE_DIR, 'output')
CHARTS_DIR = os.path.join(OUTPUT_DIR, 'charts')
os.makedirs(CHARTS_DIR, exist_ok=True)

# ============ 中文字体配置 ============
plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'SimSun', 'KaiTi']
plt.rcParams['axes.unicode_minus'] = False

# 验证字体可用
font_available = False
for font_name in ['SimHei', 'Microsoft YaHei']:
    if any(font_name in f.name for f in font_manager.fontManager.ttflist):
        font_available = True
        plt.rcParams['font.sans-serif'] = [font_name]
        print(f'使用字体: {font_name}')
        break
if not font_available:
    print('警告: 未找到中文字体，图表中文可能显示为方块')

# ============ 中文停用词 ============
STOPWORDS = set([
    '的', '了', '在', '是', '我', '有', '和', '就', '不', '人', '都', '一', '一个',
    '上', '也', '很', '到', '说', '要', '去', '你', '会', '着', '没有', '看', '好',
    '自己', '这', '他', '她', '那', '它', '们', '吗', '吧', '啊', '呢', '哦', '嗯',
    '什么', '怎么', '如何', '这个', '那个', '这些', '那些', '哪个', '哪些', '为什么',
    '还', '又', '而', '但', '但是', '却', '跟', '与', '及', '或', '而且', '因为',
    '所以', '如果', '虽然', '不过', '可以', '已经', '可能', '应该', '还是', '只是',
    '比', '把', '被', '让', '给', '从', '对', '向', '为', '以', '等', '过',
    '比较', '真的', '其实', '感觉', '觉得', '知道', '看到', '以为', '时候', '出来',
    '一下', '一点', '一直', '一些', '这样', '那样', '这么', '那么', '非常', '太',
    '最', '更', '没', '能', '想', '这部', '电影', '片子', '片', '部', '电影院',
    '场', '中', '里', '后', '前', '多', '少', '大', '小', '来', '去', '去',
    '做', '走', '完', '开始', '最后', '然', '而且', '进', '出', '起', '发',
    '影', '看', '看完', '看吧', '观', '观后', '评分', '评', '分', '星',
    '豆瓣', '豆瓣网', '评论', '短评', '打分', '推荐', '力荐', '较差', '还行',
    '看这', '去看', '别', '还有', '整个', '全', '个', '头', '家',
    '哈哈', '哈哈哈', '哈哈哈哈', '嘿嘿', '呵呵', '唉', '哎',
    '么', '啦', '呀', '哎哟', '天', '哪', '嘿', '喂',
    '《', '》', '...', '…', '。', '，', '！', '？', '、', '：', '；',
    '（', '）', '“', '”', '\n', '\r', '\t', ' ', '', 'nbsp',
])


# ============ 数据加载 ============
print('=' * 60)
print('加载数据...')
print('=' * 60)

# 加载电影信息
info_df = pd.read_csv(os.path.join(CLEAN_DIR, 'movies_info.csv'))
print(f'电影信息: {len(info_df)} 部')

# 加载所有评论
comments_list = []
csvs = sorted(glob.glob(os.path.join(CLEAN_DIR, '*_comments.csv')))
for f in csvs:
    df = pd.read_csv(f)
    comments_list.append(df)
all_comments = pd.concat(comments_list, ignore_index=True)
all_comments['评论时间'] = pd.to_datetime(all_comments['评论时间'], errors='coerce')
all_comments['用户评分'] = pd.to_numeric(all_comments['用户评分'], errors='coerce')
print(f'评论总数: {len(all_comments)} 条')

# 合并电影信息与评分
movie_scores = info_df[['片名', '年份', '豆瓣评分', '类型', '导演']].copy()
movie_scores['年份'] = movie_scores['年份'].astype(int)


# ============ 1. 豆瓣评分趋势分析 ============
print('\n' + '=' * 60)
print('1. 豆瓣评分趋势分析')
print('=' * 60)

# 每部电影的平均用户评分（来自评论）
user_rating_stats = all_comments.groupby('电影名称').agg(
    用户平均分=('用户评分', 'mean'),
    评分中位数=('用户评分', 'median'),
    评论数=('用户评分', 'count'),
    评分标准差=('用户评分', 'std')
).reset_index()

trend_df = movie_scores.merge(user_rating_stats, left_on='片名', right_on='电影名称', how='left')
trend_df = trend_df.sort_values(['年份', '豆瓣评分'], ascending=[True, False])
trend_df = trend_df.drop(columns=['电影名称'])

# 年度统计
yearly_stats = trend_df.groupby('年份').agg(
    年均豆瓣评分=('豆瓣评分', 'mean'),
    年均用户评分=('用户平均分', 'mean'),
    电影数量=('片名', 'count'),
    最高分=('豆瓣评分', 'max'),
    最低分=('豆瓣评分', 'min'),
    评分极差=('豆瓣评分', lambda x: x.max() - x.min())
).reset_index()

print(trend_df[['片名', '年份', '豆瓣评分', '用户平均分', '评论数']].to_string(index=False))

trend_df.to_csv(os.path.join(OUTPUT_DIR, 'trend_analysis.csv'), index=False, encoding='utf-8-sig')
print(f'\n已保存: trend_analysis.csv')


# ============ 2. 年度平均评分分析 ============
print('\n' + '=' * 60)
print('2. 年度平均评分分析')
print('=' * 60)
print(yearly_stats.to_string(index=False))

# 评分分布
rating_dist = all_comments.groupby('用户评分').size().reset_index(name='评论数')
rating_dist.columns = ['评分', '评论数']
print('\n评分分布:')
print(rating_dist.to_string(index=False))


# ============ 3. 情感分析 ============
print('\n' + '=' * 60)
print('3. 情感分析 (SnowNLP)')
print('=' * 60)

def get_sentiment(text):
    """获取情感得分 0-1，越接近1越正面"""
    try:
        text = str(text).strip()
        if len(text) < 2:
            return 0.5
        s = SnowNLP(text)
        return round(s.sentiments, 4)
    except:
        return 0.5

print('正在进行情感分析（可能需要几分钟）...')
all_comments['情感得分'] = all_comments['评论内容'].apply(get_sentiment)

# 情感分类
def classify_sentiment(score):
    if score >= 0.7:
        return '正面'
    elif score >= 0.4:
        return '中性'
    else:
        return '负面'

all_comments['情感分类'] = all_comments['情感得分'].apply(classify_sentiment)

# 每部电影的情感统计
sentiment_stats = all_comments.groupby('电影名称').agg(
    平均情感得分=('情感得分', 'mean'),
    正面比例=('情感分类', lambda x: (x == '正面').sum() / len(x)),
    中性比例=('情感分类', lambda x: (x == '中性').sum() / len(x)),
    负面比例=('情感分类', lambda x: (x == '负面').sum() / len(x))
).reset_index()

# 合并年份
movie_year_map = all_comments[['电影名称', '上映年份']].drop_duplicates()
sentiment_stats = sentiment_stats.merge(movie_year_map, on='电影名称')
sentiment_stats = sentiment_stats.sort_values('上映年份')

sentiment_stats.to_csv(os.path.join(OUTPUT_DIR, 'sentiment_analysis.csv'), index=False, encoding='utf-8-sig')
print(f'已保存: sentiment_analysis.csv')
print('\n情感分析摘要:')
for _, row in sentiment_stats.iterrows():
    print(f'  {row["电影名称"]:<20} 情感={row["平均情感得分"]:.2f}  正面={row["正面比例"]:.1%}  负面={row["负面比例"]:.1%}')

# 按年份统计情感
yearly_sentiment = all_comments.groupby('上映年份').agg(
    平均情感=('情感得分', 'mean'),
    正面率=('情感分类', lambda x: (x == '正面').sum() / len(x)),
    中性率=('情感分类', lambda x: (x == '中性').sum() / len(x)),
    负面率=('情感分类', lambda x: (x == '负面').sum() / len(x))
).reset_index()
yearly_sentiment.columns = ['年份', '平均情感', '正面率', '中性率', '负面率']
print('\n年度情感趋势:')
print(yearly_sentiment.to_string(index=False))


# ============ 4. 负面评论识别 ============
print('\n' + '=' * 60)
print('4. 负面评论识别')
print('=' * 60)

# 负面评论：用户评分<=2 或 情感得分<=0.3
negative_comments = all_comments[
    (all_comments['用户评分'] <= 2) | (all_comments['情感得分'] <= 0.3)
].copy()
print(f'负面评论总数: {len(negative_comments)} 条 (占 {len(negative_comments)/len(all_comments)*100:.1f}%)')

# 每部电影负面评论数
neg_by_movie = negative_comments.groupby('电影名称').size().reset_index(name='负面评论数')
neg_total = all_comments.groupby('电影名称').size().reset_index(name='总评论数')
neg_stats = neg_total.merge(neg_by_movie, on='电影名称', how='left').fillna(0)
neg_stats['负面比例'] = neg_stats['负面评论数'] / neg_stats['总评论数']
neg_stats = neg_stats.sort_values('负面比例', ascending=False)
print('\n各电影负面评论比例:')
for _, row in neg_stats.head(15).iterrows():
    print(f'  {row["电影名称"]:<20} 负面={row["负面评论数"]:>3.0f}/{row["总评论数"]:>3.0f} ({row["负面比例"]:.1%})')


# ============ 5. 高频词统计 ============
print('\n' + '=' * 60)
print('5. 高频词统计 (jieba)')
print('=' * 60)

def tokenize(text):
    """中文分词，去停用词"""
    text = str(text)
    words = jieba.lcut(text)
    words = [w.strip() for w in words if len(w.strip()) >= 2 and w.strip() not in STOPWORDS]
    return words

# 全部评论高频词
print('分词中...')
all_comments['分词'] = all_comments['评论内容'].apply(tokenize)

# 全部高频词
all_words = [w for words in all_comments['分词'] for w in words]
word_freq = Counter(all_words)
print(f'\n全部评论高频词 Top 30:')
for word, freq in word_freq.most_common(30):
    print(f'  {word:<12} {freq:>5}')

# 负面评论高频词
negative_comments = all_comments[
    (all_comments['用户评分'] <= 2) | (all_comments['情感得分'] <= 0.3)
].copy()
if '分词' not in negative_comments.columns:
    negative_comments['分词'] = negative_comments['评论内容'].apply(tokenize)
neg_words = [w for words in negative_comments['分词'] for w in words]
neg_word_freq = Counter(neg_words)
print(f'\n负面评论高频词 Top 30:')
for word, freq in neg_word_freq.most_common(30):
    print(f'  {word:<12} {freq:>5}')


# ============ 6. LDA主题分析 ============
print('\n' + '=' * 60)
print('6. LDA主题分析（负面评论）')
print('=' * 60)

# 构建负面评论文档
neg_docs = [' '.join(words) for words in negative_comments['分词'] if len(words) >= 3]
print(f'用于LDA分析的负面评论文档数: {len(neg_docs)}')

if len(neg_docs) >= 50:
    vectorizer = TfidfVectorizer(max_features=500, min_df=3, max_df=0.9)
    tfidf_matrix = vectorizer.fit_transform(neg_docs)
    feature_names = vectorizer.get_feature_names_out()

    n_topics = 6
    lda_model = LatentDirichletAllocation(n_components=n_topics, random_state=42, max_iter=20)
    lda_matrix = lda_model.fit_transform(tfidf_matrix)

    topics_data = []
    for topic_idx, topic in enumerate(lda_model.components_):
        top_words_idx = topic.argsort()[-10:][::-1]
        top_words = [feature_names[i] for i in top_words_idx]
        top_weights = [topic[i] for i in top_words_idx]
        print(f'  主题{topic_idx + 1}: {", ".join(top_words)}')
        for w, weight in zip(top_words, top_weights):
            topics_data.append({
                '主题': topic_idx + 1,
                '关键词': w,
                '权重': round(weight, 2)
            })

    topics_df = pd.DataFrame(topics_data)
    topics_df.to_csv(os.path.join(OUTPUT_DIR, 'negative_topics.csv'), index=False, encoding='utf-8-sig')
    print(f'\n已保存: negative_topics.csv')
else:
    print('负面评论不足，跳过LDA分析')


# ============ 7. 高口碑 vs 低口碑对比 ============
print('\n' + '=' * 60)
print('7. 高口碑 vs 低口碑电影对比')
print('=' * 60)

median_score = movie_scores['豆瓣评分'].median()
high_movies = movie_scores[movie_scores['豆瓣评分'] >= median_score + 0.5]['片名'].tolist()
low_movies = movie_scores[movie_scores['豆瓣评分'] <= median_score - 0.5]['片名'].tolist()

# 如果没选出足够的，用上下四分位
if len(high_movies) < 3:
    q75 = movie_scores['豆瓣评分'].quantile(0.75)
    high_movies = movie_scores[movie_scores['豆瓣评分'] >= q75]['片名'].tolist()
if len(low_movies) < 3:
    q25 = movie_scores['豆瓣评分'].quantile(0.25)
    low_movies = movie_scores[movie_scores['豆瓣评分'] <= q25]['片名'].tolist()

print(f'高口碑电影 (豆瓣评分>={movie_scores[movie_scores["片名"].isin(high_movies)]["豆瓣评分"].min():.1f}):')
for m in high_movies:
    score = movie_scores[movie_scores['片名'] == m]['豆瓣评分'].values[0]
    print(f'  {m}: {score}')
print(f'\n低口碑电影 (豆瓣评分<={movie_scores[movie_scores["片名"].isin(low_movies)]["豆瓣评分"].max():.1f}):')
for m in low_movies:
    score = movie_scores[movie_scores['片名'] == m]['豆瓣评分'].values[0]
    print(f'  {m}: {score}')

# 对比分析
high_comments = all_comments[all_comments['电影名称'].isin(high_movies)]
low_comments = all_comments[all_comments['电影名称'].isin(low_movies)]

compare_data = {
    '指标': ['平均豆瓣评分', '平均用户评分(评论)', '平均情感得分', '正面评论比例', '负面评论比例',
             '平均评论长度', '平均点赞数', '评论总数'],
    '高口碑电影': [
        f'{high_comments.merge(movie_scores[["片名","豆瓣评分"]], left_on="电影名称", right_on="片名")["豆瓣评分"].mean():.2f}',
        f'{high_comments["用户评分"].mean():.2f}',
        f'{high_comments["情感得分"].mean():.3f}',
        f'{(high_comments["情感分类"]=="正面").mean():.1%}',
        f'{(high_comments["情感分类"]=="负面").mean():.1%}',
        f'{high_comments["评论内容"].str.len().mean():.0f}',
        f'{high_comments["点赞数"].mean():.0f}',
        f'{len(high_comments)}',
    ],
    '低口碑电影': [
        f'{low_comments.merge(movie_scores[["片名","豆瓣评分"]], left_on="电影名称", right_on="片名")["豆瓣评分"].mean():.2f}',
        f'{low_comments["用户评分"].mean():.2f}',
        f'{low_comments["情感得分"].mean():.3f}',
        f'{(low_comments["情感分类"]=="正面").mean():.1%}',
        f'{(low_comments["情感分类"]=="负面").mean():.1%}',
        f'{low_comments["评论内容"].str.len().mean():.0f}',
        f'{low_comments["点赞数"].mean():.0f}',
        f'{len(low_comments)}',
    ]
}
compare_df = pd.DataFrame(compare_data)
print('\n对比分析:')
print(compare_df.to_string(index=False))

# 高口碑高频词 vs 低口碑高频词
high_words = [w for words in high_comments['分词'] for w in words]
low_words = [w for words in low_comments['分词'] for w in words]
high_freq = Counter(high_words).most_common(20)
low_freq = Counter(low_words).most_common(20)
print(f'\n高口碑电影高频词: {", ".join([f"{w}({c})" for w, c in high_freq[:15]])}')
print(f'低口碑电影高频词: {", ".join([f"{w}({c})" for w, c in low_freq[:15]])}')


# ============ 生成图表 ============
print('\n' + '=' * 60)
print('生成可视化图表...')
print('=' * 60)

# --- 图表1: 评分趋势图 ---
fig, axes = plt.subplots(2, 1, figsize=(16, 14))

# 上图：各电影评分散点
ax1 = axes[0]
for year in sorted(trend_df['年份'].unique()):
    subset = trend_df[trend_df['年份'] == year]
    ax1.scatter(subset['片名'], subset['豆瓣评分'], s=100, label=f'{year}年', zorder=3)
    for _, row in subset.iterrows():
        ax1.annotate(f'{row["豆瓣评分"]}', (row['片名'], row['豆瓣评分']),
                     textcoords="offset points", xytext=(0, 8), ha='center', fontsize=7)

ax1.set_title('2021-2026年春节档电影豆瓣评分趋势', fontsize=16, fontweight='bold')
ax1.set_ylabel('豆瓣评分', fontsize=12)
ax1.set_xlabel('')
ax1.tick_params(axis='x', rotation=45)
ax1.legend(title='年份', bbox_to_anchor=(1.02, 1), loc='upper left')
ax1.set_ylim(4, 9.5)
ax1.grid(True, alpha=0.3, axis='y')
ax1.axhline(y=7, color='green', linestyle='--', alpha=0.5, label='7分线(良好)')
ax1.axhline(y=6, color='orange', linestyle='--', alpha=0.5, label='6分线(及格)')

# 下图：年度平均评分折线
ax2 = axes[1]
years = yearly_stats['年份'].values
ax2.plot(years, yearly_stats['年均豆瓣评分'], 'o-', linewidth=2.5, markersize=10,
         label='年均豆瓣评分', color='#E74C3C')
ax2.plot(years, yearly_stats['年均用户评分'] * 2, 's--', linewidth=2, markersize=8,
         label='年均用户评分(×2)', color='#3498DB')

for i, year in enumerate(years):
    ax2.annotate(f'{yearly_stats.iloc[i]["年均豆瓣评分"]:.2f}',
                 (year, yearly_stats.iloc[i]['年均豆瓣评分']),
                 textcoords="offset points", xytext=(0, 12), ha='center', fontsize=10, fontweight='bold')

ax2.set_title('年度平均评分变化趋势', fontsize=16, fontweight='bold')
ax2.set_ylabel('平均评分', fontsize=12)
ax2.set_xlabel('年份', fontsize=12)
ax2.set_ylim(4, 9)
ax2.legend(fontsize=11)
ax2.grid(True, alpha=0.3)
ax2.set_xticks(years)

plt.tight_layout()
plt.savefig(os.path.join(CHARTS_DIR, '评分趋势图.png'), dpi=150, bbox_inches='tight')
plt.close()
print('  [OK] 评分趋势图.png')


# --- 图表2: 情感分布图 ---
fig, axes = plt.subplots(2, 2, figsize=(16, 14))

# 2a: 总体情感饼图
ax = axes[0, 0]
sentiment_counts = all_comments['情感分类'].value_counts()
colors = {'正面': '#2ECC71', '中性': '#F39C12', '负面': '#E74C3C'}
ax.pie(sentiment_counts.values, labels=sentiment_counts.index, autopct='%1.1f%%',
       colors=[colors[k] for k in sentiment_counts.index],
       startangle=90, textprops={'fontsize': 12})
ax.set_title('总体情感分布', fontsize=14, fontweight='bold')

# 2b: 年度情感趋势
ax = axes[0, 1]
x_pos = np.arange(len(yearly_sentiment))
width = 0.25
ax.bar(x_pos - width, yearly_sentiment['正面率'], width, label='正面', color='#2ECC71')
ax.bar(x_pos, yearly_sentiment['中性率'], width, label='中性', color='#F39C12')
ax.bar(x_pos + width, yearly_sentiment['负面率'], width, label='负面', color='#E74C3C')
ax.set_xticks(x_pos)
ax.set_xticklabels(yearly_sentiment['年份'].astype(int))
ax.set_title('年度情感比例对比', fontsize=14, fontweight='bold')
ax.set_ylabel('比例')
ax.legend()
ax.grid(True, alpha=0.3, axis='y')

# 2c: 各电影情感得分排名
ax = axes[1, 0]
sent_sorted = sentiment_stats.sort_values('平均情感得分')
colors_bar = ['#E74C3C' if s < 0.5 else '#F39C12' if s < 0.6 else '#2ECC71'
              for s in sent_sorted['平均情感得分']]
ax.barh(range(len(sent_sorted)), sent_sorted['平均情感得分'], color=colors_bar)
ax.set_yticks(range(len(sent_sorted)))
ax.set_yticklabels(sent_sorted['电影名称'], fontsize=8)
ax.set_title('各电影平均情感得分', fontsize=14, fontweight='bold')
ax.set_xlabel('情感得分 (0=负面, 1=正面)')
ax.axvline(x=0.5, color='gray', linestyle='--', alpha=0.5)
ax.grid(True, alpha=0.3, axis='x')

# 2d: 用户评分 vs 情感得分散点
ax = axes[1, 1]
movie_sentiment = sentiment_stats.merge(
    all_comments.groupby('电影名称')['用户评分'].mean().reset_index().rename(columns={'用户评分': '用户均分'}),
    on='电影名称'
)
ax.scatter(movie_sentiment['用户均分'], movie_sentiment['平均情感得分'],
           s=100, c='#3498DB', alpha=0.7, edgecolors='black', linewidth=0.5)
for _, row in movie_sentiment.iterrows():
    ax.annotate(row['电影名称'], (row['用户均分'], row['平均情感得分']),
                textcoords="offset points", xytext=(5, 3), fontsize=6, alpha=0.8)
ax.set_title('用户评分 vs 情感得分', fontsize=14, fontweight='bold')
ax.set_xlabel('平均用户评分 (1-5星)')
ax.set_ylabel('平均情感得分')
ax.grid(True, alpha=0.3)

plt.tight_layout()
plt.savefig(os.path.join(CHARTS_DIR, '情感分布图.png'), dpi=150, bbox_inches='tight')
plt.close()
print('  [OK] 情感分布图.png')


# --- 图表3: 年度对比图 ---
fig, axes = plt.subplots(2, 2, figsize=(16, 14))

# 3a: 年度评分箱线图
ax = axes[0, 0]
year_groups = []
year_labels = []
for year in sorted(all_comments['上映年份'].unique()):
    data = all_comments[all_comments['上映年份'] == year]['用户评分'].dropna()
    if len(data) > 0:
        year_groups.append(data.values)
        year_labels.append(str(int(year)))
bp = ax.boxplot(year_groups, labels=year_labels, patch_artist=True)
colors_box = ['#E74C3C', '#3498DB', '#2ECC71', '#F39C12', '#9B59B6', '#1ABC9C']
for patch, color in zip(bp['boxes'], colors_box[:len(bp['boxes'])]):
    patch.set_facecolor(color)
    patch.set_alpha(0.6)
ax.set_title('年度用户评分分布', fontsize=14, fontweight='bold')
ax.set_ylabel('用户评分 (1-5星)')
ax.set_xlabel('年份')
ax.grid(True, alpha=0.3, axis='y')

# 3b: 年度负面率对比
ax = axes[0, 1]
neg_rate_by_year = all_comments.groupby('上映年份').apply(
    lambda x: pd.Series({
        '低分率(1-2星)': (x['用户评分'] <= 2).sum() / len(x),
        '中分率(3星)': (x['用户评分'] == 3).sum() / len(x),
        '高分率(4-5星)': (x['用户评分'] >= 4).sum() / len(x)
    })
).reset_index()
x_pos = np.arange(len(neg_rate_by_year))
width = 0.25
ax.bar(x_pos - width, neg_rate_by_year['高分率(4-5星)'], width, label='高分(4-5星)', color='#2ECC71')
ax.bar(x_pos, neg_rate_by_year['中分率(3星)'], width, label='中分(3星)', color='#F39C12')
ax.bar(x_pos + width, neg_rate_by_year['低分率(1-2星)'], width, label='低分(1-2星)', color='#E74C3C')
ax.set_xticks(x_pos)
ax.set_xticklabels(neg_rate_by_year['上映年份'].astype(int))
ax.set_title('年度评分结构对比', fontsize=14, fontweight='bold')
ax.set_ylabel('比例')
ax.legend()
ax.grid(True, alpha=0.3, axis='y')

# 3c: 高口碑 vs 低口碑对比雷达图改为柱状图
ax = axes[1, 0]
compare_items = ['情感得分', '正面比例', '负面比例']
high_vals = [high_comments['情感得分'].mean(),
             (high_comments['情感分类'] == '正面').mean(),
             (high_comments['情感分类'] == '负面').mean()]
low_vals = [low_comments['情感得分'].mean(),
            (low_comments['情感分类'] == '正面').mean(),
            (low_comments['情感分类'] == '负面').mean()]
x_pos = np.arange(len(compare_items))
width = 0.3
bars1 = ax.bar(x_pos - width/2, high_vals, width, label='高口碑', color='#2ECC71')
bars2 = ax.bar(x_pos + width/2, low_vals, width, label='低口碑', color='#E74C3C')
ax.set_xticks(x_pos)
ax.set_xticklabels(compare_items)
ax.set_title('高口碑 vs 低口碑电影对比', fontsize=14, fontweight='bold')
ax.legend()
ax.grid(True, alpha=0.3, axis='y')
for bar in bars1:
    ax.text(bar.get_x() + bar.get_width()/2., bar.get_height() + 0.01,
            f'{bar.get_height():.2f}', ha='center', fontsize=9)
for bar in bars2:
    ax.text(bar.get_x() + bar.get_width()/2., bar.get_height() + 0.01,
            f'{bar.get_height():.2f}', ha='center', fontsize=9)

# 3d: 各年份电影豆瓣评分对比
ax = axes[1, 1]
for year in sorted(movie_scores['年份'].unique()):
    subset = movie_scores[movie_scores['年份'] == year]
    ax.scatter([year]*len(subset), subset['豆瓣评分'], s=120, alpha=0.8, zorder=3)
    for _, row in subset.iterrows():
        ax.annotate(row['片名'], (year, row['豆瓣评分']),
                    textcoords="offset points", xytext=(10, 0), fontsize=6, alpha=0.7)

ax.set_title('各年份电影豆瓣评分分布', fontsize=14, fontweight='bold')
ax.set_ylabel('豆瓣评分')
ax.set_xlabel('年份')
ax.set_ylim(4, 9.5)
ax.grid(True, alpha=0.3)
ax.axhline(y=7, color='green', linestyle='--', alpha=0.3)
ax.axhline(y=6, color='orange', linestyle='--', alpha=0.3)

plt.tight_layout()
plt.savefig(os.path.join(CHARTS_DIR, '年度对比图.png'), dpi=150, bbox_inches='tight')
plt.close()
print('  [OK] 年度对比图.png')


# --- 图表4: 负面词云图 ---
fig, axes = plt.subplots(1, 2, figsize=(18, 8))

# 获取字体路径
font_path = None
for fp in font_manager.findSystemFonts():
    if 'simhei' in fp.lower() or 'msyh' in fp.lower():
        font_path = fp
        break

# 4a: 负面评论词云
if neg_word_freq:
    wc = WordCloud(
        font_path=font_path,
        width=900, height=500,
        background_color='white',
        max_words=100,
        colormap='Reds',
        max_font_size=120,
        random_state=42
    )
    wc.generate_from_frequencies(neg_word_freq)
    axes[0].imshow(wc, interpolation='bilinear')
    axes[0].set_title('负面评论词云', fontsize=16, fontweight='bold')
    axes[0].axis('off')

# 4b: 全部评论词云
if word_freq:
    wc2 = WordCloud(
        font_path=font_path,
        width=900, height=500,
        background_color='white',
        max_words=100,
        colormap='viridis',
        max_font_size=120,
        random_state=42
    )
    wc2.generate_from_frequencies(word_freq)
    axes[1].imshow(wc2, interpolation='bilinear')
    axes[1].set_title('全部评论词云', fontsize=16, fontweight='bold')
    axes[1].axis('off')

plt.tight_layout()
plt.savefig(os.path.join(CHARTS_DIR, '负面词云图.png'), dpi=150, bbox_inches='tight')
plt.close()
print('  [OK] 负面词云图.png')


# ============ 保存汇总数据 ============
# 情感分析完整数据
sentiment_detail = all_comments[['评论ID', '电影名称', '上映年份', '用户评分',
                                   '情感得分', '情感分类', '评论内容']].copy()
sentiment_detail.to_csv(os.path.join(OUTPUT_DIR, 'sentiment_analysis_detail.csv'),
                        index=False, encoding='utf-8-sig')
print(f'\n  [OK] sentiment_analysis_detail.csv (详细情感数据)')

# 高频词统计输出
top_words_df = pd.DataFrame(word_freq.most_common(100), columns=['词语', '频次'])
top_words_df.to_csv(os.path.join(OUTPUT_DIR, '高频词统计.csv'), index=False, encoding='utf-8-sig')
print(f'  [OK] 高频词统计.csv')

neg_top_words_df = pd.DataFrame(neg_word_freq.most_common(100), columns=['词语', '频次'])
neg_top_words_df.to_csv(os.path.join(OUTPUT_DIR, '负面高频词统计.csv'), index=False, encoding='utf-8-sig')
print(f'  [OK] 负面高频词统计.csv')

# 口碑对比
compare_df.to_csv(os.path.join(OUTPUT_DIR, '口碑对比分析.csv'), index=False, encoding='utf-8-sig')
print(f'  [OK] 口碑对比分析.csv')


print('\n' + '=' * 60)
print('全部分析完成！')
print('=' * 60)
print(f'\n输出文件:')
print(f'  CSV文件:')
print(f'    - output/trend_analysis.csv          (评分趋势)')
print(f'    - output/sentiment_analysis.csv       (情感分析汇总)')
print(f'    - output/sentiment_analysis_detail.csv (情感分析明细)')
print(f'    - output/negative_topics.csv          (负面主题LDA)')
print(f'    - output/高频词统计.csv               (全部高频词)')
print(f'    - output/负面高频词统计.csv            (负面高频词)')
print(f'    - output/口碑对比分析.csv              (高vs低口碑对比)')
print(f'\n  图表文件:')
print(f'    - output/charts/评分趋势图.png')
print(f'    - output/charts/情感分布图.png')
print(f'    - output/charts/年度对比图.png')
print(f'    - output/charts/负面词云图.png')
