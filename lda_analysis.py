"""
负面评价LDA主题建模分析
========================
对春节档电影负面评论进行深度主题挖掘
判断标准：用户评分≤2星 或 情感得分<0.4
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
from gensim import corpora
from gensim.models import LdaModel
from gensim.models import CoherenceModel

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager

warnings.filterwarnings('ignore')

# ============ 配置 ============
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CLEAN_DIR = os.path.join(BASE_DIR, 'data', 'cleaned')
OUTPUT_DIR = os.path.join(BASE_DIR, 'output')
CHARTS_DIR = os.path.join(OUTPUT_DIR, 'charts')
os.makedirs(CHARTS_DIR, exist_ok=True)

plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei']
plt.rcParams['axes.unicode_minus'] = False

N_TOPICS = 5
TOP_WORDS = 15

# ============ 停用词表 ============
STOPWORDS = set([
    # 基础虚词
    '的', '了', '在', '是', '我', '有', '和', '就', '不', '人', '都', '一', '一个',
    '上', '也', '很', '到', '说', '要', '去', '你', '会', '着', '没有', '看', '好',
    '自己', '这', '他', '她', '那', '它', '们', '吗', '吧', '啊', '呢', '哦', '嗯',
    '什么', '怎么', '如何', '这个', '那个', '这些', '那些', '哪个', '哪些', '为什么',
    '还', '又', '而', '但', '但是', '却', '跟', '与', '及', '或', '而且', '因为',
    '所以', '如果', '虽然', '不过', '可以', '已经', '可能', '应该', '还是', '只是',
    '比', '把', '被', '让', '给', '从', '对', '向', '为', '以', '等', '过',
    # 常见无意义词
    '比较', '真的', '其实', '感觉', '觉得', '知道', '看到', '以为', '时候', '出来',
    '一下', '一点', '一直', '一些', '这样', '那样', '这么', '那么', '非常', '太',
    '最', '更', '没', '能', '想', '做', '走', '完', '开始', '最后', '然', '进',
    '出', '起', '发', '来', '多', '少', '大', '小', '里', '中', '后', '前',
    # 电影相关无意义词
    '影', '看', '看完', '看吧', '观', '观后', '评分', '评', '分', '星',
    '豆瓣', '豆瓣网', '评论', '短评', '打分', '推荐', '力荐', '较差', '还行',
    '看这', '去看', '别', '还有', '整个', '全', '个', '头', '家',
    '部', '电影', '片子', '片', '电影院', '场',
    # 语气词
    '哈哈', '哈哈哈', '哈哈哈哈', '嘿嘿', '呵呵', '唉', '哎',
    '么', '啦', '呀', '哎哟', '天', '哪', '嘿', '喂',
    # 标点符号
    '《', '》', '...', '…', '。', '，', '！', '？', '、', '：', '；',
    '（', '）', '“', '”', '\n', '\r', '\t', ' ', '', 'nbsp',
    # 补充停用词
    '这个片子', '一部', '这种', '就是', '不是', '没有', '一样', '不能',
    '完全', '为了', '很多', '两位', '第一', '第二', '那些', '大概',
    '以前', '之后', '以前', '以后', '起来', '通过', '不同',
])


# ============ 加载数据 ============
print('=' * 60)
print('负面评价LDA主题建模分析')
print('=' * 60)

# 加载清洗后的评论
print('\n[1/6] 加载评论数据...')
csvs = sorted(glob.glob(os.path.join(CLEAN_DIR, '*_comments.csv')))
comments_list = []
for f in csvs:
    df = pd.read_csv(f)
    comments_list.append(df)
all_comments = pd.concat(comments_list, ignore_index=True)
all_comments['用户评分'] = pd.to_numeric(all_comments['用户评分'], errors='coerce')
all_comments['评论时间'] = pd.to_datetime(all_comments['评论时间'], errors='coerce')
print(f'  总评论数: {len(all_comments)}')

# 加载情感分析结果（如果已有）
sentiment_file = os.path.join(OUTPUT_DIR, 'sentiment_analysis_detail.csv')
if os.path.exists(sentiment_file):
    print('  发现已有情感分析结果，加载中...')
    sentiment_df = pd.read_csv(sentiment_file)
    # 合并情感得分
    all_comments = all_comments.merge(
        sentiment_df[['评论ID', '情感得分']].drop_duplicates('评论ID'),
        on='评论ID', how='left'
    )
    print(f'  情感数据合并完成')
else:
    print('  未找到情感分析结果，仅使用评分筛选')
    all_comments['情感得分'] = 0.5  # 默认值


# ============ 筛选负面评论 ============
print('\n[2/6] 筛选负面评论...')
print(f'  筛选标准: 用户评分≤2星 或 情感得分<0.4')

mask = (all_comments['用户评分'] <= 2) | (all_comments['情感得分'] < 0.4)
negative = all_comments[mask].copy()
negative = negative.dropna(subset=['评论内容'])

print(f'  负面评论数: {len(negative)} 条')
print(f'  占总评论: {len(negative)/len(all_comments)*100:.1f}%')

# 统计每部电影的负面评论数
neg_count = negative.groupby('电影名称').size().reset_index(name='负面数')
neg_count = neg_count.sort_values('负面数', ascending=False)
print(f'\n  各电影负面评论数:')
for _, row in neg_count.iterrows():
    print(f'    {row["电影名称"]:<22} {row["负面数"]:>4}条')


# ============ 中文分词 ============
print('\n[3/6] 中文分词与去停用词...')

def tokenize_and_filter(text):
    """分词并去停用词，保留有意义的词语"""
    text = str(text)
    # 去除URL、@、#等
    text = re.sub(r'http\S+', '', text)
    text = re.sub(r'@\S+', '', text)
    text = re.sub(r'#\S+#', '', text)
    
    words = jieba.lcut(text)
    # 过滤：长度>=2、不在停用词中、不是纯数字
    words = [w.strip() for w in words 
             if len(w.strip()) >= 2 
             and w.strip() not in STOPWORDS
             and not w.strip().isdigit()
             and not re.match(r'^[\W_]+$', w)]
    return words

negative['分词结果'] = negative['评论内容'].apply(tokenize_and_filter)

# 过滤空列表
negative = negative[negative['分词结果'].apply(len) >= 3].copy()
print(f'  分词后有效文档数: {len(negative)}')

# 预览高频词
all_neg_words = [w for words in negative['分词结果'] for w in words]
neg_freq = Counter(all_neg_words)
print(f'  词汇总数: {len(all_neg_words)}, 去重: {len(neg_freq)}')
print(f'  高频词Top20:')
for w, c in neg_freq.most_common(20):
    print(f'    {w:<14} {c:>5}')


# ============ 构建词典与语料库 ============
print('\n[4/6] 构建LDA语料库...')

texts = negative['分词结果'].tolist()

# 构建词典
dictionary = corpora.Dictionary(texts)

# 过滤极端词频：出现少于5次的、出现在超过50%文档中的
dictionary.filter_extremes(no_below=5, no_above=0.5)
print(f'  词典大小: {len(dictionary)} 个词')

# 构建词袋模型
corpus = [dictionary.doc2bow(text) for text in texts]
# 过滤空文档
valid_corpus = [bow for bow in corpus if len(bow) > 0]
print(f'  有效文档数: {len(valid_corpus)}')


# ============ LDA建模 ============
print(f'\n[5/6] 训练LDA模型 ({N_TOPICS}个主题)...')

lda_model = LdaModel(
    corpus=valid_corpus,
    id2word=dictionary,
    num_topics=N_TOPICS,
    random_state=42,
    passes=20,          # 迭代次数
    iterations=100,
    alpha='auto',       # 自动学习alpha
    eta='auto',         # 自动学习eta
    per_word_topics=True
)

# 计算一致性分数
try:
    coherence_model = CoherenceModel(
        model=lda_model, 
        texts=texts, 
        dictionary=dictionary, 
        coherence='c_v',
        processes=1  # Windows下单进程避免freeze_support问题
    )
    coherence_score = coherence_model.get_coherence()
    print(f'  主题一致性分数 (C_v): {coherence_score:.4f}')
except Exception as e:
    coherence_score = 0.0
    print(f'  主题一致性计算跳过: {e}')


# ============ 提取主题 ============
print(f'\n[6/6] 提取主题关键词...\n')

# 主题命名映射（根据关键词自动判断 + 人工校验提示）
TOPIC_NAMES = {
    0: '导演风格与视听体验问题',
    1: '剧情逻辑与叙事结构问题',
    2: '导演个人风格与角色塑造问题',
    3: '观影期待落差与情绪失望',
    4: '喜剧类型与商业化过度问题',
}

topics_data = []
topic_keywords = {}

for idx in range(N_TOPICS):
    topic = lda_model.show_topic(idx, topn=TOP_WORDS)
    topic_keywords[idx] = topic
    
    print(f'主题{idx + 1}:')
    for word, weight in topic:
        print(f'  {word:<12} {weight:.4f}')
    print()

# 基于关键词自动命名
def auto_name_topic(keywords):
    """根据主题关键词自动命名"""
    words = [w for w, _ in keywords]
    word_set = set(words)
    
    # 剧情逻辑类
    if word_set & {'剧情', '逻辑', '漏洞', '设定', '叙事', '剧本', '故事', '情节', '节奏', '不合理'}:
        return '剧情逻辑与叙事问题'
    
    # 演员表演类
    if word_set & {'演技', '表演', '尴尬', '台词', '演员', '尴尬', '演', '出演'}:
        return '演员表演问题'
    
    # 导演创作类
    if word_set & {'导演', '镜头', '剪辑', '画面', '配乐', '节奏', '视听'}:
        return '导演创作与制作问题'
    
    # 烂片/失望类
    if word_set & {'烂片', '失望', '难看', '无聊', '不行', '如坐针毡', '烂'}:
        return '观影体验与情绪宣泄'
    
    # 类型/审美类
    if word_set & {'搞笑', '喜剧', '笑点', '煽情', '强行', '尴尬', '幽默'}:
        return '类型元素与审美问题'
    
    # 商业/营销类
    if word_set & {'春节', '票房', '营销', 'IP', '续集', '圈钱', '割韭菜'}:
        return '商业营销与IP消耗'
    
    # 角色人物类
    if word_set & {'角色', '人物', '反派', '主角', '塑造', '工具人', '人设'}:
        return '角色塑造与人物问题'
    
    # 特效制作类
    if word_set & {'特效', 'CG', '动画', '画面', '制作', '技术'}:
        return '制作技术与视觉效果'
    
    return '其他负面评价'

# 自动命名
for idx in range(N_TOPICS):
    TOPIC_NAMES[idx] = auto_name_topic(topic_keywords[idx])

# 收集所有主题数据
for idx in range(N_TOPICS):
    topic = lda_model.show_topic(idx, topn=TOP_WORDS)
    topic_name = TOPIC_NAMES[idx]
    for rank, (word, weight) in enumerate(topic, 1):
        topics_data.append({
            '主题编号': idx + 1,
            '主题名称': topic_name,
            '关键词': word,
            '权重': round(weight, 4),
            '排名': rank
        })

topics_df = pd.DataFrame(topics_data)

# 打印最终结果
print('=' * 60)
print('LDA主题建模结果')
print('=' * 60)
for idx in range(N_TOPICS):
    name = TOPIC_NAMES[idx]
    topic = lda_model.show_topic(idx, topn=10)
    keywords_str = ', '.join([f'{w}({weight:.3f})' for w, weight in topic])
    print(f'\n主题{idx + 1}: {name}')
    print(f'  关键词: {keywords_str}')


# ============ 主题分布计算 ============
print('\n' + '=' * 60)
print('主题分布')
print('=' * 60)

# 计算每条评论的主要主题
topic_counts = [0] * N_TOPICS
topic_weights = [0.0] * N_TOPICS

for bow in valid_corpus:
    doc_topics = lda_model.get_document_topics(bow)
    if doc_topics:
        # 找到概率最大的主题
        dominant_topic = max(doc_topics, key=lambda x: x[1])
        topic_counts[dominant_topic[0]] += 1
        # 累计权重
        for topic_id, prob in doc_topics:
            topic_weights[topic_id] += prob

total_docs = sum(topic_counts)
print(f'\n各主题文档分布:')
topic_summary = []
for idx in range(N_TOPICS):
    name = TOPIC_NAMES[idx]
    count = topic_counts[idx]
    pct = count / total_docs * 100 if total_docs > 0 else 0
    avg_weight = topic_weights[idx] / len(valid_corpus) if len(valid_corpus) > 0 else 0
    print(f'  主题{idx + 1} [{name}]: {count}篇 ({pct:.1f}%)')
    topic_summary.append({
        '主题编号': idx + 1,
        '主题名称': name,
        '文档数': count,
        '占比': round(pct, 1),
        '平均权重': round(avg_weight, 4)
    })

topic_summary_df = pd.DataFrame(topic_summary)


# ============ 保存CSV ============
print('\n' + '=' * 60)
print('保存结果...')
print('=' * 60)

# 保存主题-关键词表
topics_df.to_csv(os.path.join(OUTPUT_DIR, 'lda_topics.csv'), index=False, encoding='utf-8-sig')
print(f'  [OK] lda_topics.csv')

# 保存主题摘要
topic_summary_df.to_csv(os.path.join(OUTPUT_DIR, 'lda_topic_summary.csv'), index=False, encoding='utf-8-sig')
print(f'  [OK] lda_topic_summary.csv')

# 保存带主题标签的负面评论
negative_with_topic = negative[['评论ID', '电影名称', '上映年份', '用户评分', '情感得分',
                                  '评论内容', '点赞数']].copy()
# 为每条评论分配主要主题
dominant_topics = []
for bow in [dictionary.doc2bow(text) for text in negative['分词结果'].tolist()]:
    if bow:
        doc_topics = lda_model.get_document_topics(bow)
        if doc_topics:
            dominant = max(doc_topics, key=lambda x: x[1])
            dominant_topics.append(dominant[0] + 1)
        else:
            dominant_topics.append(0)
    else:
        dominant_topics.append(0)

negative_with_topic['主要主题'] = dominant_topics
negative_with_topic['主题名称'] = negative_with_topic['主要主题'].map(
    lambda x: TOPIC_NAMES.get(x-1, '未知') if x > 0 else '未知'
)
negative_with_topic.to_csv(os.path.join(OUTPUT_DIR, 'negative_comments_with_topics.csv'),
                            index=False, encoding='utf-8-sig')
print(f'  [OK] negative_comments_with_topics.csv')


# ============ 生成图表 ============
print('\n' + '=' * 60)
print('生成可视化图表...')
print('=' * 60)

colors = ['#E74C3C', '#3498DB', '#2ECC71', '#F39C12', '#9B59B6']

# --- 图表1: 主题分布柱状图 ---
fig, ax = plt.subplots(figsize=(12, 7))

names = [TOPIC_NAMES[i] for i in range(N_TOPICS)]
counts = [topic_counts[i] for i in range(N_TOPICS)]
pcts = [c / total_docs * 100 for c in counts]

bars = ax.bar(range(N_TOPICS), counts, color=colors, edgecolor='white', linewidth=1.5)

# 添加数值标签
for i, (bar, count, pct) in enumerate(zip(bars, counts, pcts)):
    ax.text(bar.get_x() + bar.get_width() / 2., bar.get_height() + 5,
            f'{count}篇\n({pct:.1f}%)',
            ha='center', va='bottom', fontsize=11, fontweight='bold')

ax.set_xticks(range(N_TOPICS))
ax.set_xticklabels(names, fontsize=11, rotation=15, ha='right')
ax.set_ylabel('负面评论数', fontsize=13)
ax.set_title('春节档电影负面评论LDA主题分布', fontsize=16, fontweight='bold')
ax.grid(True, alpha=0.3, axis='y')
ax.set_ylim(0, max(counts) * 1.2)

# 添加信息注释
ax.text(0.98, 0.95,
        f'负面评论总数: {len(negative)}条\n主题一致性(C_v): {coherence_score:.4f}\n主题数: {N_TOPICS}',
        transform=ax.transAxes, ha='right', va='top',
        fontsize=10, bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.5))

plt.tight_layout()
plt.savefig(os.path.join(CHARTS_DIR, '主题分布柱状图.png'), dpi=150, bbox_inches='tight')
plt.close()
print('  [OK] 主题分布柱状图.png')

# --- 图表2: 主题占比饼图 ---
fig, ax = plt.subplots(figsize=(10, 8))

# 按占比排序
sorted_data = sorted(zip(names, counts, pcts, colors), key=lambda x: x[1], reverse=True)
sorted_names = [d[0] for d in sorted_data]
sorted_counts = [d[1] for d in sorted_data]
sorted_pcts = [d[2] for d in sorted_data]
sorted_colors = [d[3] for d in sorted_data]

explode = [0.05] * N_TOPICS  # 轻微突出

wedges, texts, autotexts = ax.pie(
    sorted_counts,
    labels=sorted_names,
    autopct=lambda pct: f'{pct:.1f}%\n({int(round(pct/100.*sum(sorted_counts)))}篇)',
    colors=sorted_colors,
    explode=explode,
    startangle=90,
    textprops={'fontsize': 11},
    pctdistance=0.75,
    labeldistance=1.12
)

# 美化百分比文字
for autotext in autotexts:
    autotext.set_fontsize(10)
    autotext.set_fontweight('bold')

ax.set_title('负面评论主题占比分布', fontsize=16, fontweight='bold', pad=20)

# 添加图例
ax.legend(
    wedges, [f'{n}: {c}篇 ({p:.1f}%)' for n, c, p in zip(sorted_names, sorted_counts, sorted_pcts)],
    title='主题分类',
    loc='center left',
    bbox_to_anchor=(1, 0.5),
    fontsize=10
)

plt.tight_layout()
plt.savefig(os.path.join(CHARTS_DIR, '主题占比饼图.png'), dpi=150, bbox_inches='tight')
plt.close()
print('  [OK] 主题占比饼图.png')

# --- 额外: 每个主题的关键词权重柱状图 ---
fig, axes = plt.subplots(1, N_TOPICS, figsize=(24, 6))

for idx in range(N_TOPICS):
    ax = axes[idx]
    topic = lda_model.show_topic(idx, topn=10)
    words = [w for w, _ in topic][::-1]
    weights = [w for _, w in topic][::-1]
    name = TOPIC_NAMES[idx]
    
    ax.barh(range(len(words)), weights, color=colors[idx], alpha=0.8, edgecolor='white')
    ax.set_yticks(range(len(words)))
    ax.set_yticklabels(words, fontsize=9)
    ax.set_title(f'主题{idx+1}: {name}', fontsize=11, fontweight='bold')
    ax.set_xlabel('权重', fontsize=9)
    ax.grid(True, alpha=0.3, axis='x')

plt.suptitle('各主题Top10关键词权重', fontsize=16, fontweight='bold', y=1.02)
plt.tight_layout()
plt.savefig(os.path.join(CHARTS_DIR, '主题关键词权重图.png'), dpi=150, bbox_inches='tight')
plt.close()
print('  [OK] 主题关键词权重图.png')


print('\n' + '=' * 60)
print('分析完成！')
print('=' * 60)
print(f'\n输出文件:')
print(f'  CSV:')
print(f'    - output/lda_topics.csv              (主题-关键词明细)')
print(f'    - output/lda_topic_summary.csv        (主题摘要)')
print(f'    - output/negative_comments_with_topics.csv (带主题标签的负面评论)')
print(f'  图表:')
print(f'    - output/charts/主题分布柱状图.png')
print(f'    - output/charts/主题占比饼图.png')
print(f'    - output/charts/主题关键词权重图.png')
