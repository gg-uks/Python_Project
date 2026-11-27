"""카프카 토픽 → MongoDB (싱크 컨슈머). 수집기와 따로 계속 띄워 둠

    nohup python load/kafka_to_mongo.py >> sink.log 2>&1 &

- 토픽에서 꺼낸 만큼 몽고에 _id 기준 ReplaceOne upsert → 같은 메시지가 두 번 와도 중복 없음
- 몽고에 다 쓴 뒤에 오프셋을 커밋 → 몽고가 잠깐 죽어도 다시 살아나면 못 넣은 것부터 이어서
- 수집이 빠르면 토픽에 쌓였다가 자기 속도대로 넣음 (카프카가 속도를 맞춰 줌)
- 문서 모양은 load_mongo.py 와 같은 함수로 만듦 → 매일 배치로 다시 넣어도 같은 문서

| 토픽 | 컬렉션 |
| omm.raw.mangae.recipes | OMM_mangae_recipes_raw |
| omm.raw.mangae.reviews | OMM_mangae_reviews_raw |
| omm.raw.youtube        | OMM_youtube_videos     |
"""
import datetime
import json
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [ROOT, os.path.join(ROOT, 'load')]
import kafka_bus as K  # noqa: E402
import load_mongo as L  # noqa: E402

ROUTE = {
    K.TOPIC_RECIPES: ('OMM_mangae_recipes_raw', L.doc_recipe),
    K.TOPIC_REVIEWS: ('OMM_mangae_reviews_raw', L.doc_review),
    K.TOPIC_YOUTUBE: ('OMM_youtube_videos', L.doc_youtube),
}


def main():
    from kafka import KafkaConsumer
    from pymongo import ReplaceOne

    servers = K.settings()
    if not servers:
        sys.exit('config.ini 에 [kafka] enabled = yes 와 bootstrap 을 적어 주세요.')
    db = L.connect()
    for name, (coll, _, idx) in L.TARGETS.items():         # 보조 인덱스도 load_mongo 와 같게
        if coll in {c for c, _ in ROUTE.values()}:
            for keys in idx:
                db[coll].create_index([(k, 1) for k in keys])
    consumer = KafkaConsumer(
        *ROUTE, bootstrap_servers=servers, group_id='omm-mongo-sink',
        enable_auto_commit=False, auto_offset_reset='earliest', max_poll_records=500,
        value_deserializer=lambda b: json.loads(b.decode('utf-8')),
    )
    print(f'[싱크] 구독: {", ".join(ROUTE)} · 그룹 omm-mongo-sink')
    total, t_last = 0, time.time()
    while True:
        batch = consumer.poll(timeout_ms=2000)
        if not batch:
            if time.time() - t_last > 600:
                print(f"[싱크] {time.strftime('%H:%M:%S')} 대기 중 (지금까지 {total:,}건)")
                t_last = time.time()
            continue
        L.NOW = datetime.datetime.now(datetime.timezone.utc)   # loaded_at = 이번에 넣은 시각
        ops = {}
        for tp, msgs in batch.items():
            coll, make = ROUTE[tp.topic]
            for m in msgs:
                d = make(m.value)
                if d:
                    ops.setdefault(coll, []).append(ReplaceOne({'_id': d['_id']}, d, upsert=True))
        while True:                                         # 몽고에 다 써야 커밋 (실패하면 30초 뒤 다시)
            try:
                for coll, o in ops.items():
                    db[coll].bulk_write(o, ordered=False)
                consumer.commit()
                break
            except Exception as e:
                print(f'[싱크] 몽고 쓰기 실패 → 30초 뒤 다시: {e!r}')
                time.sleep(30)
        n = sum(len(o) for o in ops.values())
        total += n
        t_last = time.time()
        print(f"[싱크] {time.strftime('%H:%M:%S')} " + ' · '.join(f'{c} {len(o)}' for c, o in ops.items())
              + f' (누적 {total:,})')


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print('멈춤. 다시 띄우면 커밋한 다음부터 이어서 넣어요.')
