"""真实AI与规则的语义、复杂需求及轻量追问演示；不代替真人评分。"""
from __future__ import annotations
import argparse
from dataclasses import asdict
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import sys
import time
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'back'))

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database',type=Path,required=True)
    parser.add_argument('--output',type=Path,default=ROOT/'outputs'/'ai-capabilities-20261012')
    args=parser.parse_args()
    db=args.database.resolve(strict=True);out=args.output.resolve();out.mkdir(parents=True,exist_ok=True)
    if (out/'records.json').exists():parser.error('已有记录，请用新输出目录，不覆盖历史结果。')
    os.environ['DATABASE_URL']=f'sqlite:///file:{db.as_posix()}?mode=ro&uri=true'
    os.environ['CONTENT_MODE']='compact'
    os.chdir(ROOT/'back')
    from sqlalchemy import create_engine
    from sqlmodel import Session
    from app.core.config import settings
    from app.schemas.ai import AiChatRequest
    from app.services import ai_service,recipe_service,weather_service
    from app.ai import client
    if not settings.ai_api_key.strip():parser.error('未配置本机模型密钥，不能演示真实AI。')
    engine=create_engine(os.environ['DATABASE_URL'])
    settings.ai_temperature=0;settings.weather_enabled=False
    weather=weather_service.current_weather(city=None,month=10,today='2026-10-12')
    frozen=datetime(2026,10,12,12)
    class FixedDateTime(datetime):
        @classmethod
        def now(cls,tz=None):return frozen.replace(tzinfo=tz)
    original_route=ai_service._route_smart;original_call=client.complete_json
    route_log=[];call_log=[];total_calls=0
    def route_capture(**kw):
        r=original_route(**kw);route_log.append(asdict(r));return r
    def model_capture(*a,**kw):
        nonlocal total_calls
        total_calls+=1
        if total_calls>16:raise RuntimeError('超过预设16次模型调用，停止演示。')
        r=original_call(*a,**kw)
        call_log.append(dict(ok=r.ok,model=r.model,ms=r.elapsed_ms,data=r.data,error=r.error))
        return r
    scenarios=[
        dict(id='S1',title='隐含的用餐需求',message='忙了一天，肚子空空的，只想要暖和又省事的一顿。',expected_intent='meal_recommendation'),
        dict(id='S2',title='采购食材而不是菜谱',message='采购单上该放些什么，才能让正在练力量的人补足蛋白质？',expected_intent='recommend_foods'),
        dict(id='S3',title='复杂条件和解释',message='今天晚餐一家三口，25分钟内，别太油，不吃海鲜和花生，最好少洗几个锅。请说清为什么适合。',cook_minutes=25,avoid=['海鲜','花生'],preferences=['清淡'],expected_intent='meal_recommendation'),
        dict(id='S4',title='只有自然语言时间条件',message='今天晚饭只剩15分钟可以做，不想吃外卖，帮我挑几道。',expected_minutes=15,expected_intent='meal_recommendation'),
        dict(id='S5',title='食材知识提问',message='莲藕有什么特点，怎么保存比较好？我只是问知识，不需要菜谱。',expected_intent='general'),
        dict(id='M1',title='多轮第一问',message='给三个人安排晚餐，25分钟以内，不吃海鲜和花生，偏清淡。',cook_minutes=25,avoid=['海鲜','花生'],preferences=['清淡'],expected_intent='meal_recommendation',sequence=True),
        dict(id='M2',title='追问换菜并新增不喝汤',message='不要汤了，换别的，其他条件不变。',cook_minutes=25,avoid=['海鲜','花生'],preferences=['清淡'],expected_intent='meal_recommendation',sequence=True,no_soup=True),
        dict(id='M3',title='继续追问保留条件',message='刚才的忌口继续保留，再换一组，不要重复。',cook_minutes=25,avoid=['海鲜','花生'],preferences=['清淡'],expected_intent='meal_recommendation',sequence=True,no_soup=True),
    ]
    # 预先记录预期，不能看输出后更换指标或删掉失败例。
    snapshot_hash=hashlib.sha256(db.read_bytes()).hexdigest()
    (out/'protocol.json').write_text(json.dumps(dict(date='2026-10-12',scenarios=scenarios,max_model_calls=16,
        database_sha256=snapshot_hash,weather=asdict(weather),temperature=0,
        context_scope='追问仅由请求携带last_intent、已展示ID和家庭档案；没有完整历史消息，不能宣称完整对话记忆。',
        evaluation='意图标签是本次预定义人工预期；单次探索，不是独立专家标注集。油量和锅数量不作自动达标判断。'),ensure_ascii=False,indent=2),encoding='utf-8')
    history={False:dict(last_intent=None,ids=[]),True:dict(last_intent=None,ids=[])}
    records=[]
    with patch.object(ai_service,'datetime',FixedDateTime),patch.object(ai_service,'_weather_for',return_value=weather),patch.object(ai_service,'_route_smart',side_effect=route_capture),patch.object(client,'complete_json',side_effect=model_capture):
        for scenario in scenarios:
            for enabled in (False,True):
                settings.ai_enabled=enabled;route_log.clear();call_log.clear()
                kwargs=dict(message=scenario['message'],people=3,cook_minutes=scenario.get('cook_minutes',45),
                            avoid=scenario.get('avoid',[]),preferences=scenario.get('preferences',[]),city=None)
                if scenario.get('sequence') and scenario['id']!='M1':
                    kwargs.update(last_intent=history[enabled]['last_intent'],recent_recipe_ids=history[enabled]['ids'])
                payload=AiChatRequest(**kwargs)
                start=time.perf_counter()
                with Session(engine) as session:
                    response=ai_service.chat(session,None,payload).model_dump()
                    ms=round((time.perf_counter()-start)*1000,1)
                    checks=[]
                    for r in response.get('recipes',[]):
                        detail=recipe_service.get_detail(session,r['id'])
                        ingredients=[i.name for i in detail.ingredients] if detail else []
                        haystack=' '.join([r['name'],*ingredients])
                        hits=[term for term in ('虾','蟹','贝','蛤','蚝','鱿鱼','鲍','海参') if term in haystack] if '海鲜' in payload.avoid else []
                        if '花生' in payload.avoid and '花生' in haystack:hits.append('花生')
                        limit=scenario.get('expected_minutes',payload.cook_minutes)
                        checks.append(dict(id=r['id'],name=r['name'],ingredients=ingredients,avoid_hits=hits,
                            duration_unknown=r['duration_estimated'],duration_minutes=r['duration_minutes'],
                            known_time_over=not r['duration_estimated'] and r['duration_minutes']>limit,
                            repeated=r['id'] in payload.recent_recipe_ids,
                            soup='汤' in r['name'] or any('汤' in t for t in r['tags'])))
                actual_route=route_log[0] if route_log else {}
                row=dict(id=scenario['id'],title=scenario['title'],version='AI' if enabled else '规则',input=payload.model_dump(),
                    expected=scenario,response=response,route=actual_route,model_calls=call_log.copy(),elapsed_ms=ms,checks=checks,
                    intent_matches=response['intent']==scenario['expected_intent'],
                    soup_mismatch=sum(c['soup'] for c in checks) if scenario.get('no_soup') else None,
                    intent_source_label_mismatch=response.get('intent_source')!=actual_route.get('source'))
                records.append(row)
                if scenario.get('sequence'):
                    history[enabled]['last_intent']=response['intent']
                    history[enabled]['ids'].extend(r['id'] for r in response.get('recipes',[]))
                (out/'records.json').write_text(json.dumps(records,ensure_ascii=False,indent=2,default=str),encoding='utf-8')
                print(json.dumps(dict(id=row['id'],version=row['version'],intent=response['intent'],route_source=actual_route.get('source'),
                    source=response['source'],recipes=len(response.get('recipes',[])),foods=len(response.get('foods',[])),
                    intent_matches=row['intent_matches'],known_time_over=sum(c['known_time_over'] for c in checks),soup_mismatch=row['soup_mismatch']),ensure_ascii=False),flush=True)
    assert hashlib.sha256(db.read_bytes()).hexdigest()==snapshot_hash
    markdown=['# AI功能实测展示','', '同本地代码和只读快照，固定2026-10-12；8个输入各测试规则与真实AI。单次探索，非总体性能证明。','',
        '|编号|功能场景|版本|预期意图|实际意图|实际路由来源|返回来源|菜/食材数|预期意图匹配|',
        '|---|---|---|---|---|---|---|---|---|']
    for r in records:
        response=r['response']
        markdown.append('|'+ '|'.join(str(x) for x in [r['id'],r['title'],r['version'],r['expected']['expected_intent'],response['intent'],r['route'].get('source'),response['source'],f"{len(response['recipes'])}/{len(response['foods'])}",'是' if r['intent_matches'] else '否'])+'|')
    markdown+=['','## 输入和实际回答','']
    for scenario in scenarios:
        markdown += [f"### {scenario['id']} {scenario['title']}",'',scenario['message'],'']
        for r in [r for r in records if r['id']==scenario['id']]:
            markdown += [f"#### {r['version']}实际输出",'',r['response']['answer'],'',
                '推荐菜：'+('、'.join(c['name'] for c in r['checks']) or '无'),
                '推荐食材：'+('、'.join(x['name'] for x in r['response']['foods']) or '无'),
                '语义识别依据：'+str(r['route'].get('why') or '规则关键词路由'),'']
            for step in r['response']['trace']:
                markdown.append(f"- {step['agent']}：{step['summary']}")
            markdown += ['', f"核查：有依据超出用户时间{sum(c['known_time_over'] for c in r['checks'])}道；忌口命中{sum(bool(c['avoid_hits']) for c in r['checks'])}道；重复{sum(c['repeated'] for c in r['checks'])}道。"]
            if r['soup_mismatch'] is not None:markdown.append(f"不喝汤条件：仍出现{r['soup_mismatch']}道汤。")
            if r['intent_source_label_mismatch']:markdown.append('标记问题：响应intent_source与实际路由来源不一致；本报告依据捕获的真实路由和调用记录，不据响应默认值假定来源。')
            markdown.append('')
    markdown+=['## 展示边界','',
        f'真实模型调用{total_calls}次；每次实际输入、返回、解析路由及检查依据均保存在records.json。',
        '自然语言意图分类、候选选择和解释生成分别记录，不把规则安全过滤或客户端传递上下文说成模型独有能力。',
        '不喝汤、少油、少洗锅等新增要求可能未进入硬约束；即使文案声称满足也不能当成验证通过。',
        '没有完整历史消息，只有上一轮意图、已展示ID、家庭档案。因此不能宣称实现完整会话记忆。',
        '解释是否更可信、更合口味仍需真人盲评。报告保留全部预定义场景和失败，不只摘成功样例。']
    (out/'AI功能实测展示.md').write_text('\n'.join(markdown)+'\n',encoding='utf-8')
    engine.dispose();print('DONE',out,flush=True)

if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    main()
