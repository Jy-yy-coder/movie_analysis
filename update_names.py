"""更新所有LDA输出CSV的主题名称"""
import pandas as pd

df = pd.read_csv('output/lda_topics.csv')
summary = pd.read_csv('output/lda_topic_summary.csv')
neg = pd.read_csv('output/negative_comments_with_topics.csv')

name_map = {
    1: '导演风格与视听体验问题',
    2: '剧情逻辑与叙事结构问题',
    3: '导演个人风格与角色塑造问题',
    4: '观影期待落差与情绪失望',
    5: '喜剧类型与商业化过度问题'
}

df['主题名称'] = df['主题编号'].map(name_map)
summary['主题名称'] = summary['主题编号'].map(name_map)
neg['主题名称'] = neg['主要主题'].map(name_map)

df.to_csv('output/lda_topics.csv', index=False, encoding='utf-8-sig')
summary.to_csv('output/lda_topic_summary.csv', index=False, encoding='utf-8-sig')
neg.to_csv('output/negative_comments_with_topics.csv', index=False, encoding='utf-8-sig')

print('全部CSV主题名称已统一更新完成')
print()
for k, v in name_map.items():
    row = summary[summary['主题编号'] == k].iloc[0]
    docs = int(row['文档数'])
    pct = row['占比']
    print(f'主题{k}: {v}')
    print(f'  文档数: {docs}篇, 占比: {pct}%')
