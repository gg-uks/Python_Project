"""수집기 → 카프카 토픽 보내기 (프로듀서)

수집기가 파일에 한 줄 쓸 때 같은 내용을 토픽에도 보냄. 파일 쓰기는 그대로라 정제는 영향 없음.
카프카가 꺼져 있거나 설정이 없으면 경고 한 번만 찍고 파일만 씀 (수집은 멈추지 않음).
못 보낸 것은 매일 load_mongo.py 가 파일에서 다시 넣으므로 빠지지 않음 (같은 _id 덮어쓰기).

config.ini
  [kafka]
  enabled = yes
  bootstrap = 10.0.56.101:9092,10.0.56.102:9092,10.0.56.103:9092

토픽 (메시지 키 = 몽고 _id, 값 = 원본 한 줄 JSON)
  omm.raw.mangae.recipes   → OMM_mangae_recipes_raw   키 recipe_id
  omm.raw.mangae.reviews   → OMM_mangae_reviews_raw   키 review_id
  omm.raw.youtube          → OMM_youtube_videos       키 run_date|query|period|video_id

확인
  python kafka_bus.py test     # 브로커 접속 · 토픽 확인
"""
import configparser
import json
import os
import sys
import threading

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paths as P  # noqa: E402

TOPIC_RECIPES = 'omm.raw.mangae.recipes'
TOPIC_REVIEWS = 'omm.raw.mangae.reviews'
TOPIC_YOUTUBE = 'omm.raw.youtube'
TOPICS = [TOPIC_RECIPES, TOPIC_REVIEWS, TOPIC_YOUTUBE]

_lock = threading.Lock()
_producer = None
_off = False          # 한 번 실패하면 이번 실행에서는 더 시도하지 않음
_sent = 0
_failed = 0


def settings():
    cfg = configparser.ConfigParser()
    cfg.read(P.CONFIG, encoding='utf-8')
    if not cfg.has_section('kafka'):
        return None
    k = cfg['kafka']
    if k.get('enabled', 'no').strip().lower() not in ('yes', 'true', '1', 'y'):
        return None
    servers = [h.strip() for h in k.get('bootstrap', '').split(',') if h.strip()]
    return servers or None


def producer():
    global _producer, _off
    if _off:
        return None
    if _producer is not None:
        return _producer
    with _lock:
        if _producer is not None or _off:
            return _producer
        servers = settings()
        if not servers:
            _off = True
            return None
        try:
            from kafka import KafkaProducer
            _producer = KafkaProducer(
                bootstrap_servers=servers,
                key_serializer=lambda k: str(k).encode('utf-8'),
                value_serializer=lambda v: json.dumps(v, ensure_ascii=False, default=str).encode('utf-8'),
                acks='all', retries=5, linger_ms=50, max_request_size=5 * 1024 * 1024,
            )
            print(f'[카프카] 연결: {", ".join(servers)}')
        except Exception as e:
            print(f'[카프카] 연결 실패 → 이번엔 파일만 씀 (매일 load_mongo.py 가 채움): {e!r}')
            _off = True
            return None
    return _producer


def _err(e):
    global _failed
    _failed += 1
    if _failed in (1, 100, 1000):
        print(f'[카프카] 보내기 실패 {_failed}건 (파일엔 저장됨): {e!r}')


def _ok(_):
    global _sent
    _sent += 1


def send(topic, key, value):
    p = producer()
    if p is None:
        return
    try:
        p.send(topic, key=key, value=value).add_callback(_ok).add_errback(_err)
    except Exception as e:
        _err(e)


def send_recipe(rec):
    send(TOPIC_RECIPES, rec['recipe_id'], rec)


def send_reviews(reviews):
    for r in reviews:
        if r.get('review_id') is not None:
            send(TOPIC_REVIEWS, r['review_id'], r)


def send_youtube(rows):
    for r in rows:
        send(TOPIC_YOUTUBE, f"{r['run_date']}|{r['query']}|{r['period']}|{r['video_id']}", r)


def flush():
    if _producer is not None:
        try:
            _producer.flush(timeout=30)
        except Exception as e:
            _err(e)
        print(f'[카프카] 보냄 {_sent:,}건 · 실패 {_failed:,}건')


def test():
    servers = settings()
    if not servers:
        sys.exit('config.ini 에 [kafka] enabled = yes 와 bootstrap 을 적어 주세요.')
    from kafka import KafkaConsumer
    c = KafkaConsumer(bootstrap_servers=servers, request_timeout_ms=15000)
    have = c.topics()
    print('브로커:', ', '.join(servers))
    for t in TOPICS:
        print(f'  {t}: {"있음" if t in have else "없음 (자동 생성이 꺼져 있으면 README 의 명령으로 만들기)"}')
    c.close()


if __name__ == '__main__':
    if sys.argv[1:] == ['test']:
        test()
    else:
        print(__doc__)
