"""
春节档电影观影决策平台 - Flask主应用
自包含版本：无需预生成分析文件，启动时自动计算
"""

import pandas as pd
import numpy as np
import os
import glob
import re
import json
from collections import Counter
from flask import Flask, render_template, jsonify, request, send_from_directory, abort
from werkzeug.utils import safe_join
from dotenv import load_dotenv

# 加载 .env 文件
load_dotenv()

app = Flask(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CLEAN_DIR = os.path.join(BASE_DIR, 'data', 'cleaned')
RAW_DIR = os.path.join(BASE_DIR, 'data', 'raw')
STATIC_POSTER_DIR = os.path.join(BASE_DIR, 'static', 'posters')
RAW_POSTER_DIR = os.path.join(RAW_DIR, 'posters')
POSTER_DIRS = [STATIC_POSTER_DIR, RAW_POSTER_DIR]

# ==================== 关键词库 ====================

POS_KEYWORDS = [
    '特效', '演技', '节奏', '笑点', '感动', '诚意', '好看', '惊喜', '视觉',
    '场面', '动画', '热血', '温馨', '搞笑', '精彩', '推荐', '喜欢', '优秀',
    '值得', '好笑', '流泪', '震撼', '用心', '良心', '经典', '创新', '细腻',
    '真实', '深刻', '氛围', '配乐', '美术', '出色', '到位', '好评', '力荐',
    '满分', '过瘾', '精良', '精致', '大气', '出色', '燃', '治愈', '舒服',
]

NEG_KEYWORDS = [
    '逻辑', '尴尬', '无聊', '难看', '煽情', '强行', '失望', '烂片', '恶心',
    '垃圾', '催眠', '浪费', '套路', '敷衍', '离谱', '混乱', '生硬', '低俗',
    '拖沓', '空洞', '浮夸', '做作', '粗糙', '狗血', '拼凑', '卖弄', '刻意',
    '雷人', '难受', '无语', '劝退', '不值', '欺骗', '装', '滥', '水', '烂',
    '差劲', '出戏', '跳戏', '败笔', '稀烂', '侮辱',
]

ALL_KEYWORDS = list(dict.fromkeys(POS_KEYWORDS + NEG_KEYWORDS + [
    '剧情', '故事', '角色', '导演', '演员', '喜剧', '动作', '科幻',
    '爱情', '悬疑', '动画', '国漫', '续集', '改编', '主旋律', '春节档',
    '3D', 'IMAX', '煽情', '反转', '结局', '开头', '高潮', '铺垫',
]))

# ==================== GitHub 配置 ====================
GITHUB_RAW_BASE = 'https://raw.githubusercontent.com/Jy-yy-coder/movie_analysis/main/data/raw/posters/'

# ==================== 工具函数 ====================

def safe_str(val):
    if val is None:
        return ''
    try:
        if pd.isna(val):
            return ''
    except (ValueError, TypeError):
        pass
    if isinstance(val, float):
        if np.isnan(val):
            return ''
        if val == int(val):
            return str(int(val))
    return str(val)


def get_label(score):
    if score >= 7.5:
        return ('口碑佳作', 'success')
    elif score >= 6.5:
        return ('中规中矩', 'warning')
    else:
        return ('差评较多', 'danger')


def normalize_name(name):
    return re.sub(r'[·：:""\s\u3000\u00a0\-—]', '', str(name))


def find_poster(name, posters):
    if not posters:
        return None
    filename = None
    if name in posters:
        filename = posters[name]
    else:
        norm = normalize_name(name)
        for k in posters:
            if normalize_name(k) == norm:
                filename = posters[k]
                break
        if not filename:
            for k in posters:
                if name in k or k in name:
                    filename = posters[k]
                    break
    # 返回 GitHub raw 链接
    if filename:
        from urllib.parse import quote
        return GITHUB_RAW_BASE + quote(filename)
    return None


def iter_poster_files():
    seen = set()
    for poster_dir in POSTER_DIRS:
        if not os.path.isdir(poster_dir):
            continue
        for filename in os.listdir(poster_dir):
            if filename in seen:
                continue
            if filename.lower().endswith(('.jpg', '.jpeg', '.png', '.webp')):
                seen.add(filename)
                yield filename


def find_poster_dir(filename):
    for poster_dir in POSTER_DIRS:
        path = safe_join(poster_dir, filename)
        if path and os.path.isfile(path):
            return poster_dir
    return None


def find_comments(name, comments_dict):
    if name in comments_dict:
        return comments_dict[name]
    norm = normalize_name(name)
    for k in comments_dict:
        if normalize_name(k) == norm:
            return comments_dict[k]
    for k in comments_dict:
        if k in name or name in k:
            return comments_dict[k]
    return pd.DataFrame()


def count_keywords_in_texts(texts, keywords):
    counts = {}
    for text in texts:
        if not isinstance(text, str):
            continue
        for kw in keywords:
            if kw in text:
                counts[kw] = counts.get(kw, 0) + 1
    return counts


def analyze_sentiment(comments_df):
    if len(comments_df) == 0:
        return {'positive': 0, 'neutral': 0, 'negative': 0, 'avg': 0, 'total': 0}
    rated = comments_df[comments_df['用户评分'] > 0]
    total = len(rated)
    if total == 0:
        return {'positive': 0, 'neutral': 0, 'negative': 0, 'avg': 0, 'total': 0}
    pos = len(rated[rated['用户评分'] >= 4])
    neg = len(rated[rated['用户评分'] <= 2])
    mid = total - pos - neg
    return {
        'positive': round(pos / total, 3),
        'neutral': round(mid / total, 3),
        'negative': round(neg / total, 3),
        'avg': round(float(rated['用户评分'].mean()), 2),
        'total': total,
    }


def gen_ai_summary(movie, sentiment, comments_df):
    score = movie['豆瓣评分']
    name = movie['片名']
    year = int(movie['年份'])

    if score >= 8.0:
        one_line = f"《{name}》豆瓣{score}分，{year}年春节档口碑佳作，观众好评如潮，强烈推荐！"
    elif score >= 7.0:
        one_line = f"《{name}》豆瓣{score}分，整体质量不错，虽有争议但瑕不掩瑜，值得一看。"
    elif score >= 6.0:
        one_line = f"《{name}》豆瓣{score}分，表现中规中矩，部分观众觉得不错但槽点也不少，建议降低期待。"
    else:
        one_line = f"《{name}》豆瓣{score}分，口碑不佳差评集中，建议慎重选择或避开。"

    if score >= 8.5:
        rec_index = 5
    elif score >= 7.5:
        rec_index = 4
    elif score >= 6.5:
        rec_index = 3
    elif score >= 5.5:
        rec_index = 2
    else:
        rec_index = 1

    pos_reasons = []
    neg_reasons = []
    top_kws = []

    if len(comments_df) > 0 and '评论内容' in comments_df.columns:
        good_texts = comments_df[comments_df['用户评分'] >= 4]['评论内容'].dropna().tolist()
        bad_texts = comments_df[comments_df['用户评分'] <= 2]['评论内容'].dropna().tolist()
        all_texts = comments_df['评论内容'].dropna().tolist()

        pos_counts = count_keywords_in_texts(good_texts, POS_KEYWORDS)
        pos_sorted = sorted(pos_counts.items(), key=lambda x: -x[1])
        pos_reasons = [{'关键词': k, '次数': v} for k, v in pos_sorted[:5] if v > 0]

        neg_counts = count_keywords_in_texts(bad_texts, NEG_KEYWORDS)
        neg_sorted = sorted(neg_counts.items(), key=lambda x: -x[1])
        neg_reasons = [{'关键词': k, '次数': v} for k, v in neg_sorted[:5] if v > 0]

        all_counts = count_keywords_in_texts(all_texts, ALL_KEYWORDS)
        all_sorted = sorted(all_counts.items(), key=lambda x: -x[1])
        top_kws = [{'词': k, '频次': v} for k, v in all_sorted[:15] if v > 0]

    if not pos_reasons:
        if score >= 7.5:
            pos_reasons = [{'关键词': '整体口碑优秀', '次数': 0}]
        elif score >= 6.5:
            pos_reasons = [{'关键词': '基本达到预期', '次数': 0}]
        else:
            pos_reasons = [{'关键词': '部分场景尚可', '次数': 0}]
    if not neg_reasons:
        if score < 6.0:
            neg_reasons = [{'关键词': '口碑较差', '次数': 0}]
        elif score < 7.5:
            neg_reasons = [{'关键词': '存在争议点', '次数': 0}]
        else:
            neg_reasons = [{'关键词': '个别情节可改进', '次数': 0}]

    return {
        '一句话评价': one_line,
        '推荐指数': rec_index,
        '推荐理由': pos_reasons,
        '避雷提醒': neg_reasons,
        '高频关键词': top_kws,
    }


# ==================== 数据加载 ====================

def load_all_data():
    print('正在加载数据...')
    data = {}

    # 1. 电影基本信息
    info_df = pd.read_csv(os.path.join(CLEAN_DIR, 'movies_info.csv'))
    info_df['年份'] = info_df['年份'].astype(int)
    info_df['豆瓣评分'] = pd.to_numeric(info_df['豆瓣评分'], errors='coerce')
    # 过滤掉2020年（非春节档范围）
    info_df = info_df[info_df['年份'] >= 2021].reset_index(drop=True)
    data['movies'] = info_df.to_dict('records')
    data['movie_by_id'] = {str(m['movie_id']): m for m in data['movies']}
    data['movie_by_name'] = {m['片名']: m for m in data['movies']}

    # 2. 海报
    data['posters'] = {}
    for f in iter_poster_files():
        data['posters'][f.rsplit('.', 1)[0]] = f

    # 3. 评论数据
    data['comments'] = {}
    for f in glob.glob(os.path.join(CLEAN_DIR, '*_comments.csv')):
        name = os.path.basename(f).replace('_comments.csv', '')
        df = pd.read_csv(f)
        df['用户评分'] = pd.to_numeric(df.get('用户评分', 0), errors='coerce').fillna(0).astype(int)
        if '点赞数' in df.columns:
            df['点赞数'] = pd.to_numeric(df['点赞数'], errors='coerce').fillna(0).astype(int)
        data['comments'][name] = df

    # 4. 情感分析 + AI总结
    print('正在分析情感和生成AI总结...')
    data['sentiment'] = {}
    data['ai_summary'] = {}
    for m in data['movies']:
        name = m['片名']
        cdf = find_comments(name, data['comments'])
        sent = analyze_sentiment(cdf)
        data['sentiment'][name] = sent
        data['ai_summary'][name] = gen_ai_summary(m, sent, cdf)

    # 5. 年度统计（仅2021-2026）
    data['yearly'] = {}
    for year in sorted(info_df['年份'].unique()):
        if year < 2021:
            continue
        ym = info_df[info_df['年份'] == year]
        year_movies = ym.to_dict('records')
        data['yearly'][int(year)] = {
            'movies': year_movies,
            'count': len(ym),
            'avg_score': round(float(ym['豆瓣评分'].mean()), 2),
            'total_comments': sum(
                len(find_comments(m['片名'], data['comments'])) for m in year_movies
            ),
        }

    data['years'] = sorted([int(y) for y in info_df['年份'].unique()])
    data['total_comments'] = sum(len(v) for v in data['comments'].values())

    print(f'数据加载完成: {len(data["movies"])}部电影, {data["total_comments"]}条评论')
    return data


DATA = load_all_data()

# ==================== 页面路由 ====================

@app.route('/')
def welcome():
    return render_template('welcome.html')


@app.route('/home')
def index():
    return render_template('index.html')


@app.route('/library')
def library():
    return render_template('movie_library.html')


@app.route('/movie/<movie_id>')
def movie_detail(movie_id):
    return render_template('movie_detail.html', movie_id=movie_id)


@app.route('/yearly')
def yearly_analysis():
    return render_template('yearly_analysis.html')

@app.route('/profile')
def profile():
    return render_template('profile.html')

@app.route('/analysis')
def reputation_analysis():
    return render_template('reputation_analysis.html')


@app.route('/compare')
def movie_compare():
    return render_template('movie_compare.html')


@app.route('/negative')
def negative_analysis():
    return render_template('negative_analysis.html')


@app.route('/yearly_compare')
def yearly_compare():
    return render_template('yearly_compare.html')


@app.route('/ai')
def ai_recommend():
    return render_template('ai_recommend.html')


# ==================== API ====================

@app.route('/api/overview')
def api_overview():
    movies = DATA['movies']
    avg_score = round(float(np.mean([m['豆瓣评分'] for m in movies])), 2)

    top10 = sorted(movies, key=lambda x: x['豆瓣评分'], reverse=True)[:10]
    top10_data = []
    for m in top10:
        label, lt = get_label(m['豆瓣评分'])
        poster = find_poster(m['片名'], DATA['posters'])
        top10_data.append({
            'movie_id': str(m['movie_id']), '片名': m['片名'],
            '年份': int(m['年份']), '豆瓣评分': float(m['豆瓣评分']),
            'label': label, 'label_type': lt, '海报': poster,
        })

    ranking = sorted(movies, key=lambda x: x['豆瓣评分'], reverse=True)
    rank_data = []
    for i, m in enumerate(ranking):
        label, lt = get_label(m['豆瓣评分'])
        rank_data.append({
            'rank': i + 1, '片名': m['片名'], '年份': int(m['年份']),
            '豆瓣评分': float(m['豆瓣评分']), 'movie_id': str(m['movie_id']),
            'label': label, 'label_type': lt,
        })

    return jsonify({
        'movie_count': len(movies),
        'total_comments': DATA['total_comments'],
        'avg_score': avg_score,
        'top10': top10_data,
        'ranking': rank_data,
    })


@app.route('/api/movies')
def api_movies():
    movies = []
    for m in DATA['movies']:
        label, lt = get_label(m['豆瓣评分'])
        poster = find_poster(m['片名'], DATA['posters'])
        sent = DATA['sentiment'].get(m['片名'], {})
        cdf = find_comments(m['片名'], DATA['comments'])
        movies.append({
            'movie_id': str(m['movie_id']),
            '片名': m['片名'],
            '年份': int(m['年份']),
            '豆瓣评分': float(m['豆瓣评分']),
            '导演': safe_str(m.get('导演', '')),
            '主演': safe_str(m.get('主演', '')),
            '类型': safe_str(m.get('类型', '')),
            '片长': safe_str(m.get('片长', '')),
            '海报': poster,
            'label': label,
            'label_type': lt,
            '正面比例': sent.get('positive', 0),
            '负面比例': sent.get('negative', 0),
            '评论数': len(cdf),
        })
    return jsonify(movies)


@app.route('/api/movie/<movie_id>')
def api_movie_detail(movie_id):
    m = DATA['movie_by_id'].get(str(movie_id))
    if not m:
        return jsonify({'error': '电影不存在'}), 404

    name = m['片名']
    year = int(m['年份'])
    label, lt = get_label(m['豆瓣评分'])
    poster = find_poster(name, DATA['posters'])
    comments_df = find_comments(name, DATA['comments'])
    sent = DATA['sentiment'].get(name, {})
    ai = DATA['ai_summary'].get(name, {})

    # 评分分布
    rating_dist = {}
    if len(comments_df) > 0:
        for r in [1, 2, 3, 4, 5]:
            rating_dist[str(r)] = int((comments_df['用户评分'] == r).sum())
        rating_dist['0'] = int((comments_df['用户评分'] == 0).sum())

    # 精选好评/差评
    good_com = []
    bad_com = []
    if len(comments_df) > 0 and '评论内容' in comments_df.columns:
        top_good = comments_df[comments_df['用户评分'] >= 4].sort_values(
            '点赞数', ascending=False).head(5)
        for _, row in top_good.iterrows():
            good_com.append({
                '用户昵称': safe_str(row.get('用户昵称', '')),
                '用户评分': int(row.get('用户评分', 0)),
                '评论内容': safe_str(row.get('评论内容', '')),
                '点赞数': int(row.get('点赞数', 0)),
                '评论时间': safe_str(row.get('评论时间', ''))[:10],
            })
        top_bad = comments_df[comments_df['用户评分'] <= 2].sort_values(
            '点赞数', ascending=False).head(5)
        for _, row in top_bad.iterrows():
            bad_com.append({
                '用户昵称': safe_str(row.get('用户昵称', '')),
                '用户评分': int(row.get('用户评分', 0)),
                '评论内容': safe_str(row.get('评论内容', '')),
                '点赞数': int(row.get('点赞数', 0)),
                '评论时间': safe_str(row.get('评论时间', ''))[:10],
            })

    # 同档期对比
    year_data = DATA['yearly'].get(year, {})
    year_movies = year_data.get('movies', [])
    yms = sorted(year_movies, key=lambda x: x['豆瓣评分'], reverse=True)
    rank = next((i + 1 for i, x in enumerate(yms) if x['片名'] == name), 0)
    same_year = []
    for ym in yms:
        ys = DATA['sentiment'].get(ym['片名'], {})
        yl, ylt = get_label(ym['豆瓣评分'])
        same_year.append({
            'movie_id': str(ym['movie_id']),
            '片名': ym['片名'],
            '豆瓣评分': float(ym['豆瓣评分']),
            'label': yl,
            'label_type': ylt,
            '负面比例': ys.get('negative', 0),
        })

    return jsonify({
        'movie_id': str(m['movie_id']),
        '片名': name,
        '年份': year,
        '导演': safe_str(m.get('导演', '')),
        '编剧': safe_str(m.get('编剧', '')),
        '主演': safe_str(m.get('主演', '')),
        '类型': safe_str(m.get('类型', '')),
        '制片国家': safe_str(m.get('制片国家/地区', '')),
        '语言': safe_str(m.get('语言', '')),
        '上映日期': safe_str(m.get('上映日期', '')),
        '片长': safe_str(m.get('片长', '')),
        '豆瓣评分': float(m['豆瓣评分']),
        '剧情简介': safe_str(m.get('剧情简介', '')),
        '海报': poster,
        'label': label,
        'label_type': lt,
        '评论总数': len(comments_df),
        '评分分布': rating_dist,
        '情感数据': sent,
        '精选好评': good_com,
        '精选差评': bad_com,
        '同档期排名': rank,
        '同档期电影数': len(yms),
        '同档期电影': same_year,
        'AI总结': ai,
    })


@app.route('/api/trends')
def api_trends():
    result = []
    for year in DATA['years']:
        yd = DATA['yearly'][year]
        sent_list = [DATA['sentiment'].get(m['片名'], {}) for m in yd['movies']]
        avg_pos = np.mean([s.get('positive', 0) for s in sent_list]) if sent_list else 0
        avg_neg = np.mean([s.get('negative', 0) for s in sent_list]) if sent_list else 0
        result.append({
            'year': year,
            'avg_score': yd['avg_score'],
            'movie_count': yd['count'],
            'total_comments': yd['total_comments'],
            'avg_positive': round(float(avg_pos), 3),
            'avg_negative': round(float(avg_neg), 3),
            'movies': [{'片名': m['片名'], '豆瓣评分': float(m['豆瓣评分'])}
                       for m in yd['movies']],
        })
    return jsonify(result)


@app.route('/api/yearly/<int:year>')
def api_yearly(year):
    yd = DATA['yearly'].get(year)
    if not yd:
        return jsonify({'error': '无数据'}), 404
    movies = []
    for m in sorted(yd['movies'], key=lambda x: x['豆瓣评分'], reverse=True):
        sent = DATA['sentiment'].get(m['片名'], {})
        label, lt = get_label(m['豆瓣评分'])
        poster = find_poster(m['片名'], DATA['posters'])
        cdf = find_comments(m['片名'], DATA['comments'])
        movies.append({
            'movie_id': str(m['movie_id']),
            '片名': m['片名'],
            '豆瓣评分': float(m['豆瓣评分']),
            'label': label,
            'label_type': lt,
            '海报': poster,
            '评论数': len(cdf),
            '正面比例': sent.get('positive', 0),
            '负面比例': sent.get('negative', 0),
            '情感得分': sent.get('avg', 0),
        })
    return jsonify({
        'year': year, 'count': yd['count'],
        'avg_score': yd['avg_score'], 'total_comments': yd['total_comments'],
        'movies': movies,
    })


@app.route('/api/yearly_all')
def api_yearly_all():
    result = []
    for year in DATA['years']:
        yd = DATA['yearly'][year]
        sent_list = [DATA['sentiment'].get(m['片名'], {}) for m in yd['movies']]
        avg_pos = np.mean([s.get('positive', 0) for s in sent_list]) if sent_list else 0
        avg_neg = np.mean([s.get('negative', 0) for s in sent_list]) if sent_list else 0
        avg_mid = np.mean([s.get('neutral', 0) for s in sent_list]) if sent_list else 0
        result.append({
            'year': year, 'count': yd['count'],
            'avg_score': yd['avg_score'], 'total_comments': yd['total_comments'],
            'avg_pos_rate': round(float(avg_pos), 3),
            'avg_neg_rate': round(float(avg_neg), 3),
            'avg_mid_rate': round(float(avg_mid), 3),
        })
    return jsonify(result)


@app.route('/api/search')
def api_search():
    q = request.args.get('q', '').strip()
    if not q:
        return jsonify([])
    results = []
    for m in DATA['movies']:
        if q in m['片名'] or q in safe_str(m.get('导演', '')) or q in safe_str(m.get('主演', '')):
            label, lt = get_label(m['豆瓣评分'])
            poster = find_poster(m['片名'], DATA['posters'])
            results.append({
                'movie_id': str(m['movie_id']),
                '片名': m['片名'],
                '年份': int(m['年份']),
                '豆瓣评分': float(m['豆瓣评分']),
                '导演': safe_str(m.get('导演', '')),
                'label': label,
                'label_type': lt,
                '海报': poster,
            })
    return jsonify(results[:10])


@app.route('/api/compare')
def api_compare():
    id1 = request.args.get('id1', '')
    id2 = request.args.get('id2', '')
    m1 = DATA['movie_by_id'].get(str(id1))
    m2 = DATA['movie_by_id'].get(str(id2))
    if not m1 or not m2:
        return jsonify({'error': '电影不存在'}), 404

    def cmp_data(m):
        name = m['片名']
        sent = DATA['sentiment'].get(name, {})
        cdf = find_comments(name, DATA['comments'])
        ai = DATA['ai_summary'].get(name, {})
        poster = find_poster(name, DATA['posters'])
        label, lt = get_label(m['豆瓣评分'])
        rd = {}
        if len(cdf) > 0:
            for r in [1, 2, 3, 4, 5]:
                rd[str(r)] = int((cdf['用户评分'] == r).sum())
        return {
            'movie_id': str(m['movie_id']), '片名': name,
            '年份': int(m['年份']), '豆瓣评分': float(m['豆瓣评分']),
            '导演': safe_str(m.get('导演', '')),
            '主演': safe_str(m.get('主演', '')),
            '类型': safe_str(m.get('类型', '')),
            '片长': safe_str(m.get('片长', '')),
            '海报': poster, 'label': label,
            '评论总数': len(cdf), '评分分布': rd,
            '情感数据': sent, 'AI总结': ai,
        }

    return jsonify({'movie1': cmp_data(m1), 'movie2': cmp_data(m2)})


@app.route('/posters/<path:filename>')
def poster(filename):
    poster_dir = find_poster_dir(filename)
    if not poster_dir:
        abort(404)
    return send_from_directory(poster_dir, filename)

# ==================== 口碑分析 API ====================

@app.route('/api/analysis-data')
def api_analysis_data():
    """获取口碑分析数据"""
    import pandas as pd
    import os
    
    output_dir = os.path.join(BASE_DIR, 'output')
    
    data = {}
    
    try:
        # 1. 年度对比数据
        trend_file = os.path.join(output_dir, 'trend_analysis.csv')
        if os.path.exists(trend_file):
            trend_df = pd.read_csv(trend_file, encoding='utf-8-sig')
            # 处理NaN值，避免JSON序列化错误
            trend_df = trend_df.fillna('')
            data['yearly_comparison'] = trend_df.to_dict('records')
        else:
            data['yearly_comparison'] = []
        
        # 2. 情感分布数据
        sentiment_file = os.path.join(output_dir, 'sentiment_analysis.csv')
        if os.path.exists(sentiment_file):
            sentiment_df = pd.read_csv(sentiment_file, encoding='utf-8-sig')
            sentiment_df = sentiment_df.fillna('')
            data['sentiment_distribution'] = sentiment_df.to_dict('records')
        else:
            data['sentiment_distribution'] = []
        
        # 3. 主题分布数据
        topics_file = os.path.join(output_dir, 'lda_topic_summary.csv')
        if os.path.exists(topics_file):
            topics_df = pd.read_csv(topics_file, encoding='utf-8-sig')
            topics_df = topics_df.fillna('')
            data['topic_distribution'] = topics_df.to_dict('records')
        else:
            data['topic_distribution'] = []
        
        # 4. 高频词统计
        keywords_file = os.path.join(output_dir, '高频词统计.csv')
        if os.path.exists(keywords_file):
            keywords_df = pd.read_csv(keywords_file, encoding='utf-8-sig')
            keywords_df = keywords_df.fillna('')
            data['high_freq_keywords'] = keywords_df.to_dict('records')
        else:
            data['high_freq_keywords'] = []
        
        # 5. 口碑对比
        reputation_file = os.path.join(output_dir, '口碑对比分析.csv')
        if os.path.exists(reputation_file):
            reputation_df = pd.read_csv(reputation_file, encoding='utf-8-sig')
            reputation_df = reputation_df.fillna('')
            data['reputation_comparison'] = reputation_df.to_dict('records')
        else:
            data['reputation_comparison'] = []
            
    except Exception as e:
        print(f'读取分析数据出错: {e}')
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500
    
    return jsonify(data)


@app.route('/api/negative_topics')
def api_negative_topics():
    """获取负面评论主题分析数据"""
    output_dir = os.path.join(BASE_DIR, 'output')
    
    # 读取主题摘要
    topics = []
    summary_file = os.path.join(output_dir, 'lda_topic_summary.csv')
    keywords_file = os.path.join(output_dir, 'negative_topics.csv')
    
    if os.path.exists(summary_file) and os.path.exists(keywords_file):
        summary_df = pd.read_csv(summary_file, encoding='utf-8-sig')
        keywords_df = pd.read_csv(keywords_file, encoding='utf-8-sig')
        
        for _, row in summary_df.iterrows():
            topic_id = row['主题编号']
            topic_keywords = keywords_df[keywords_df['主题'] == topic_id]
            keywords_list = [{'词': r['关键词'], '权重': float(r['权重'])} for _, r in topic_keywords.iterrows()]
            
            topics.append({
                '主题编号': int(topic_id),
                '主题名称': row['主题名称'],
                '文档数': int(row['文档数']),
                '占比': float(row['占比']),
                '关键词': keywords_list
            })
    
    # 读取电影-主题矩阵
    matrix = []
    detail_file = os.path.join(output_dir, 'negative_comments_with_topics.csv')
    if os.path.exists(detail_file):
        detail_df = pd.read_csv(detail_file, encoding='utf-8-sig')
        
        # 按电影和主题分组统计
        movie_topic_counts = detail_df.groupby(['电影名称', '主题名称']).size().reset_index(name='count')
        
        # 获取每个电影的负面评论总数
        movie_totals = detail_df.groupby('电影名称').size().reset_index(name='负面总数')
        
        # 构建矩阵数据
        for movie_name in movie_totals['电影名称'].unique():
            movie_data = movie_topic_counts[movie_topic_counts['电影名称'] == movie_name]
            total = int(movie_totals[movie_totals['电影名称'] == movie_name]['负面总数'].values[0])
            
            topic_dist = {}
            for _, row in movie_data.iterrows():
                topic_dist[row['主题名称']] = int(row['count'])
            
            matrix.append({
                '片名': movie_name,
                '负面总数': total,
                '主题分布': topic_dist
            })
    
    return jsonify({
        'topics': topics,
        'movie_topic_matrix': matrix
    })


# ==================== AI 推荐 API ====================

# SenseNova API 配置
SENSENOVA_API_KEY = os.environ.get('SENSENOVA_API_KEY', '')
SENSENOVA_BASE_URL = 'https://token.sensenova.cn/v1'

@app.route('/api/recommend', methods=['POST'])
def api_recommend():
    """AI 智能推荐电影"""
    data = request.get_json()
    user_mood = data.get('mood', '').strip()
    
    if not user_mood:
        return jsonify({'error': '请输入你的心情或需求'}), 400
    
    if not SENSENOVA_API_KEY:
        return jsonify({'error': 'AI 服务未配置，请设置 SENSENOVA_API_KEY 环境变量'}), 500
    
    # 获取电影数据
    movies = DATA['movies']
    movies_info = []
    for m in movies:
        label, lt = get_label(m['豆瓣评分'])
        poster = find_poster(m['片名'], DATA['posters'])
        movies_info.append({
            '片名': m['片名'],
            '年份': int(m['年份']),
            '豆瓣评分': float(m['豆瓣评分']),
            '导演': safe_str(m.get('导演', '')),
            '主演': safe_str(m.get('主演', '')),
            '类型': safe_str(m.get('类型', '')),
            '剧情简介': safe_str(m.get('剧情简介', ''))[:200],
            '海报': poster,
            'label': label
        })
    
    # 构建 prompt
    system_prompt = """你是一个专业的电影推荐助手。用户会告诉你他们的心情、想法或需求，你需要从提供的春节档电影列表中推荐最合适的电影。

请按以下格式返回 JSON：
{
  "summary": "对用户需求的理解和推荐总结（1-2句话）",
  "recommendations": [
    {
      "片名": "电影名称",
      "理由": "推荐理由（2-3句话，说明为什么这部电影适合用户当前的心情/需求）"
    }
  ]
}

规则：
1. 只推荐列表中存在的电影
2. 推荐 2-4 部最匹配的电影
3. 理由要具体、有说服力
4. 返回纯 JSON，不要包含其他文字"""

    user_prompt = f"""用户需求：{user_mood}

可选电影列表：
{json.dumps(movies_info, ensure_ascii=False, indent=2)}"""
    
    try:
        from openai import OpenAI
        
        client = OpenAI(
            api_key=SENSENOVA_API_KEY,
            base_url=SENSENOVA_BASE_URL
        )
        
        response = client.chat.completions.create(
            model='sensenova-6.7-flash-lite',
            messages=[
                {'role': 'system', 'content': system_prompt},
                {'role': 'user', 'content': user_prompt}
            ],
            temperature=0.7,
            max_tokens=1000
        )
        
        ai_response = response.choices[0].message.content
        
        # 解析 JSON 响应
        try:
            # 尝试提取 JSON
            json_match = re.search(r'\{[\s\S]*\}', ai_response)
            if json_match:
                result = json.loads(json_match.group())
            else:
                result = json.loads(ai_response)
            
            # 补充电影详细信息
            for rec in result.get('recommendations', []):
                movie_name = rec.get('片名', '')
                for m in movies_info:
                    if m['片名'] == movie_name:
                        rec['年份'] = m['年份']
                        rec['豆瓣评分'] = m['豆瓣评分']
                        rec['导演'] = m['导演']
                        rec['海报'] = m['海报']
                        break
            
            return jsonify(result)
            
        except json.JSONDecodeError:
            # JSON 解析失败，返回原始响应
            return jsonify({
                'summary': ai_response,
                'recommendations': []
            })
    
    except Exception as e:
        print(f'AI 推荐错误: {e}')
        return jsonify({'error': f'AI 服务调用失败: {str(e)}'}), 500


if __name__ == '__main__':
    print('春节档电影观影决策平台启动中...')
    app.run(debug=False, host='0.0.0.0', port=5000)
