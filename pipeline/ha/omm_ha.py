#!/usr/bin/env python3
"""OMM 백엔드 2대(back1 · back2) 배치 작업 자동 전환 (설치 위치: /opt/pipeline/ha/omm_ha.py, root 로 실행)

평소:  수집기(omm-collector)는 back1, 노멀라이저(daily.sh, 20:30)는 back2. 싱크(omm-sink)는 두 대 모두 (Kafka 소비자 그룹이 나눔).
한 대가 꺼지면: 남은 서버가 두 역할을 다 함. 살아 돌아와도 역할을 바로 뺏어 오지 않음 (왔다 갔다 방지).

  watch        감시 (systemd omm-ha.service 가 계속 돌림)
               - Valkey 키 omm:ha:collector = 수집기 주인 (임대 TTL, 주인이 CHECK 초마다 갱신)
               - 주인만 omm-collector 를 켜고, 아니면 끔. Valkey 가 안 되면 받아 둔 임대가 끝날 때 스스로 끔
               - 주인은 SYNC 초마다 수집기 폴더(진행 기록 · KAMIS 캐시)를 상대 서버로 rsync (상대가 이어받을 수 있게)
  normalizer   노멀라이저 한 번 (cron: 20:30 --slot main, 21:30 · 23:30 --slot backup. 수집기 18:00 일일 작업이 몽고에 넣은 뒤)
               - 오늘 이미 성공(omm_etl_runs mart_python_v4 ETL_OK)했으면 건너뜀
                 "성공" = 수집 일일 작업이 끝난 뒤(collector/data/raw/daily_done.txt 수정 시각)의 성공. 끝난 게 없으면 12:00 뒤
               - 수집 일일 작업이 아직 안 끝났으면 NORMALIZER_WAIT_UNTIL(22:30)까지 기다림 (넘으면 그냥 돌림, 수집이 나중에 끝나면 23:30 에 다시)
               - main 은 우선 서버만, backup 은 누구든. PostgreSQL advisory lock 으로 두 대가 동시에 못 돌게
               - 성공하면 노멀라이저 폴더(사전 · 코드)를 상대 서버로 rsync
  status       지금 역할 · 임대 · 서비스 상태
  슬랙 알림     문제 · 평소와 다를 때만 바로 보냄 (정상 결과는 22:00 check_daily 요약). /opt/pipeline/slack.env 의 SLACK_WEBHOOK_URL
               수집기 주인 바뀜 · Valkey 끊겨 수집기 멈춤 · 노멀라이저 실패 · 수집 기다림 · 어제 수집분으로 돌림 · 대신 돌린 노멀라이저 결과
  handover     수집기를 상대에게 넘김 (점검할 때). 이 서버는 PAUSE 초 동안 다시 안 잡음
  sync         지금 바로 rsync (수집기 주인이면 수집기, --normalizer 면 노멀라이저 폴더)

시험: --dry-run (systemctl · rsync · daily.sh 를 실행하지 않고 로그만), --me back2 (호스트 이름 대신), --prefix (Valkey 키 앞부분)
"""
import argparse
import json
import logging
import os
import signal
import socket
import subprocess
import sys
import threading
import time
import urllib.request
from datetime import datetime
from pathlib import Path

API_DIR = "/opt/pipeline/api"
HA_DIR = Path("/opt/pipeline/ha")
CONF = {                                     # /opt/pipeline/ha/ha.conf (KEY=VALUE) 로 덮어씀
    "HOSTS": "back1,back2",                  # 두 서버 이름 (hostname -s 소문자)
    "PREFER_COLLECTOR": "back1",
    "PREFER_NORMALIZER": "back2",
    "LEASE_TTL": "45",                       # 임대 시간 (초). 주인이 죽으면 이만큼 뒤에 상대가 이어받음
    "CHECK": "10",                           # 감시 주기 (초)
    "GRACE": "30",                           # 우선 서버가 아닌 쪽은 임대가 비고 이만큼 더 기다린 뒤 잡음
    "SYNC": "600",                           # 수집기 폴더 rsync 주기 (초)
    "PAUSE": "300",                          # handover 뒤 이 서버가 다시 잡지 않는 시간 (초)
    "SYNC_USER": "ommsync",
    "SYNC_KEY": "/opt/pipeline/ha/sync_key",
    "COLLECTOR_DIR": "/opt/pipeline/collector",
    "NORMALIZER_DIR": "/opt/pipeline/normalizer",
    "NORMALIZER_USER": "admina",
    "NORMALIZER_DAY_START": "12:00",         # 오늘 이 시각 뒤에 성공한 기록이 있으면 '오늘 끝남'
    "NORMALIZER_TIMEOUT": "14400",           # 노멀라이저 최대 실행 시간 (초)
    "NORMALIZER_WAIT_UNTIL": "22:30",        # 수집 일일 작업이 안 끝났으면 이 시각까지 기다림 (넘으면 어제 수집분으로라도 돌림)
    "NORMALIZER_WAIT_POLL": "300",           # 기다리는 동안 확인 주기 (초)
    "SLACK_NOTIFY": "1",                     # 0 이면 슬랙 알림 안 보냄
    "SLACK_ENV": "/opt/pipeline/slack.env",  # SLACK_WEBHOOK_URL (adminb:wheel 660, check_daily.sh 와 같은 웹훅)
}
COLLECTOR_EXCLUDE = ["logs/", "*.log", "collect.lock", "__pycache__/", "*.pyc"]
NORMALIZER_EXCLUDE = ["logs/", ".venv/", "backups/", "__pycache__/", "*.pyc", "*.log"]
PG_LOCK = 7_500_001                          # pg_try_advisory_lock 번호 (노멀라이저)
RENEW_LUA = "if redis.call('get', KEYS[1]) == ARGV[1] then return redis.call('pexpire', KEYS[1], ARGV[2]) else return 0 end"
RELEASE_LUA = "if redis.call('get', KEYS[1]) == ARGV[1] then return redis.call('del', KEYS[1]) else return 0 end"

log = logging.getLogger("omm-ha")


def load_env():
    """omm-api.env (DB · Valkey 접속) + ha.conf"""
    for path in (Path(API_DIR) / "omm-api.env", HA_DIR / "ha.conf"):
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                v = v.strip().strip("'\"")
                if path.name == "ha.conf":
                    CONF[k.strip()] = v
                else:
                    os.environ.setdefault(k.strip(), v)
    for k in CONF:                           # 시험용: OMM_HA_LEASE_TTL=6 처럼 환경변수로 덮어쓰기
        if os.environ.get("OMM_HA_" + k):
            CONF[k] = os.environ["OMM_HA_" + k]


def valkey():
    sys.path.insert(0, API_DIR)
    from app import cache                    # API 와 같은 Sentinel 설정 · 비밀번호
    r = cache._connect()
    r.ping()
    return r


def pg():
    import psycopg
    return psycopg.connect("", autocommit=True, connect_timeout=5)


class Ctx:
    def __init__(self, a):
        self.dry = a.dry_run
        self.me = (a.me or socket.gethostname().split(".")[0]).lower()
        hosts = [h.strip() for h in CONF["HOSTS"].split(",")]
        if self.me not in hosts:
            sys.exit(f"이 서버({self.me})가 HOSTS({hosts})에 없어요. --me 또는 ha.conf 확인")
        self.peer = next(h for h in hosts if h != self.me)
        self.key = f"{a.prefix}:collector"
        self.pause_key = f"{a.prefix}:pause:{self.me}"
        self.ttl_ms = int(CONF["LEASE_TTL"]) * 1000

    def run(self, cmd, **kw):
        if self.dry:
            log.info("[dry-run] %s", " ".join(cmd))
            return subprocess.CompletedProcess(cmd, 0, "", "")
        return subprocess.run(cmd, capture_output=True, text=True, **kw)

    # systemd
    def active(self, unit):
        if self.dry:
            return getattr(self, "_fake_" + unit.replace("-", "_"), False)
        return subprocess.run(["systemctl", "is-active", "--quiet", unit]).returncode == 0

    def set_unit(self, unit, on):
        if self.active(unit) == on:
            return
        log.warning("%s %s", unit, "켬 (이 서버가 맡음)" if on else "끔 (상대가 맡음 / 임대 없음)")
        r = self.run(["systemctl", "start" if on else "stop", unit])
        if r.returncode:
            log.error("systemctl 실패: %s", r.stderr.strip())
        if self.dry:
            setattr(self, "_fake_" + unit.replace("-", "_"), on)

    def rsync(self, src, exclude, wait=False):
        # 받는 쪽은 ommsync → sudo rrsync /opt/pipeline (root 로 받되 /opt/pipeline 안만). -a 로 시각 · 소유자까지 그대로:
        # 수집기 load_mongo 가 KAMIS 캐시 파일 시각을 보고 새 파일만 올리므로 시각이 바뀌면 넘겨받은 뒤 전부 다시 올림
        cmd = ["rsync", "-a", "--numeric-ids", "--partial", "--timeout=60",
               "-e", f"ssh -i {CONF['SYNC_KEY']} -o BatchMode=yes -o ConnectTimeout=5 -o StrictHostKeyChecking=accept-new "
                     f"-o UserKnownHostsFile={HA_DIR}/known_hosts"]
        rel = os.path.relpath(src.rstrip("/"), "/opt/pipeline")      # rrsync 는 /opt/pipeline 기준 경로만 받음
        cmd += [f"--exclude={e}" for e in exclude] + [src.rstrip("/") + "/", f"{CONF['SYNC_USER']}@{self.peer}:{rel}/"]
        if self.dry:
            log.info("[dry-run] %s", " ".join(cmd))
            return None
        if wait:
            r = subprocess.run(cmd, capture_output=True, text=True)
            (log.info if r.returncode == 0 else log.error)("rsync %s → %s: %s %s", src, self.peer,
                                                            "끝" if r.returncode == 0 else f"실패({r.returncode})", r.stderr.strip()[-200:])
            return r
        return subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)


def notify(ctx, icon, title, detail="", wait=True):
    """슬랙 알림 (문제 · 평소와 다를 때만). 실패해도 작업은 계속 — 로그만 남김. --dry-run 이면 OMM_HA_SLACK_ENV 를 따로 줄 때만 보냄 (시험용)"""
    msg = f"{icon} *OMM {title}* · {ctx.me} · {datetime.now():%m/%d %H:%M}" + (f"\n{detail}" if detail else "")
    if CONF["SLACK_NOTIFY"] != "1" or (ctx.dry and not os.environ.get("OMM_HA_SLACK_ENV")):
        log.info("[슬랙 안 보냄] %s", msg.replace("\n", " / "))
        return
    def send():
        try:
            url = ""
            for line in Path(CONF["SLACK_ENV"]).read_text(encoding="utf-8").splitlines():
                k, _, v = line.strip().partition("=")
                if k.strip() == "SLACK_WEBHOOK_URL":
                    url = v.strip().strip("'\"")
            if not url:
                log.warning("슬랙: %s 에 SLACK_WEBHOOK_URL 이 없음", CONF["SLACK_ENV"])
                return
            req = urllib.request.Request(url, json.dumps({"text": msg}).encode(), {"Content-Type": "application/json; charset=utf-8"})
            with urllib.request.urlopen(req, timeout=5) as resp:
                body = resp.read().decode(errors="replace")
            (log.info if body == "ok" else log.warning)("슬랙 보냄: %s (%s)", title, body[:50])
        except Exception as e:
            log.warning("슬랙 못 보냄: %s (%s)", title, e)
    if wait:
        send()
    else:                                    # 감시 반복을 막지 않게 따로
        threading.Thread(target=send, daemon=True).start()


def write_status(ctx, **kw):
    if ctx.dry:
        return
    try:
        Path("/run/omm-ha").mkdir(exist_ok=True)
        Path("/run/omm-ha/status.json").write_text(json.dumps({"me": ctx.me, "at": datetime.now().isoformat(timespec="seconds"), **kw},
                                                              ensure_ascii=False))
    except OSError:
        pass


# ── 수집기 감시 ───────────────────────────────────────────────────────────────
def watch(ctx, once=False):
    check, grace, sync_every = int(CONF["CHECK"]), int(CONF["GRACE"]), int(CONF["SYNC"])
    prefer = CONF["PREFER_COLLECTOR"] == ctx.me
    r, holder, valid_until, empty_since, last_sync, sync_proc = None, False, 0.0, None, 0.0, None
    seen_peer, valkey_alerted = False, False   # 상대가 주인인 걸 본 적 있음 / Valkey 끊김 알림 보냄
    stop = {"now": False}
    signal.signal(signal.SIGTERM, lambda *_: stop.update(now=True))
    log.info("감시 시작: 나=%s 상대=%s 수집기 우선=%s 키=%s", ctx.me, ctx.peer, CONF["PREFER_COLLECTOR"], ctx.key)
    while not stop["now"]:
        now = time.monotonic()
        try:
            if r is None:
                r = valkey()
                if valkey_alerted:
                    valkey_alerted = False
                    notify(ctx, "✅", "Valkey 다시 연결됨", "수집기 주인 정하기가 다시 돎", wait=False)
            if holder and r.eval(RENEW_LUA, 1, ctx.key, ctx.me, ctx.ttl_ms):
                valid_until = now + ctx.ttl_ms / 1000
            else:
                if holder:
                    log.warning("임대를 잃음 (다른 서버가 가져감)")
                holder = False
                owner = r.get(ctx.key)
                if owner == ctx.me and r.eval(RENEW_LUA, 1, ctx.key, ctx.me, ctx.ttl_ms):   # 감시만 다시 켜진 경우: 내 임대 그대로
                    holder, valid_until = True, now + ctx.ttl_ms / 1000
                    log.warning("남아 있던 내 임대를 이어 씀")
                elif owner is None:
                    empty_since = empty_since or now
                    paused = r.exists(ctx.pause_key)
                    if not paused and (prefer or now - empty_since >= grace) and r.set(ctx.key, ctx.me, nx=True, px=ctx.ttl_ms):
                        holder, valid_until, empty_since = True, now + ctx.ttl_ms / 1000, None
                        log.warning("수집기 주인이 됨 (%s)", "우선 서버" if prefer else f"임대가 {grace}초 넘게 비어 있어 이어받음")
                        # 알림: 상대 → 나 로 바뀐 경우만 (감시 재시작 · 부팅 때 우선 서버가 다시 잡는 건 조용히)
                        if seen_peer or not prefer:
                            planned = bool(r.exists(f"{ctx.key.rsplit(':', 1)[0]}:pause:{ctx.peer}"))
                            if planned:
                                notify(ctx, "ℹ️", f"수집기 주인 바뀜 {ctx.peer} → {ctx.me}", f"{ctx.peer} 에서 handover(점검)로 넘김", wait=False)
                            else:
                                notify(ctx, "⚠️", f"수집기 주인 바뀜 {ctx.peer} → {ctx.me}",
                                       f"{ctx.peer} 임대가 끝남 (서버 · omm-ha 응답 없음) → {ctx.me} 가 이어받아 수집 중\n"
                                       + (f"{ctx.peer} 상태 확인" if prefer else
                                          f"{ctx.peer} 상태 확인 · 정상이 되면 {ctx.me} 에서 `omm_ha.py handover` 로 되돌리기"), wait=False)
                        seen_peer = False
                else:
                    empty_since = None
                    seen_peer = (owner.decode() if isinstance(owner, bytes) else owner) == ctx.peer
        except Exception as e:                       # Valkey 접속 실패 → 받아 둔 임대 시간까지만 주인
            r = None
            if holder and now >= valid_until:
                holder = False
                log.error("Valkey 연결 안 됨 · 임대 끝 → 수집기 끔: %s", e)
                if not valkey_alerted:
                    valkey_alerted = True
                    notify(ctx, "❌", "Valkey 연결 안 됨 → 수집기 멈춤",
                           f"수집기 주인을 정할 수 없어 {ctx.me} 수집기를 껐어요 (두 서버가 같이 수집하지 않게). Valkey(Sentinel) 확인", wait=False)
            else:
                log.error("Valkey 연결 안 됨: %s", e)
        ctx.set_unit("omm-collector", holder)
        if sync_proc is not None and sync_proc.poll() is not None:      # 끝난 rsync 정리 · 결과 기록
            err = (sync_proc.stderr.read() or "").strip().splitlines()
            (log.info if sync_proc.returncode == 0 else log.warning)(
                "rsync 수집기 폴더 → %s: %s", ctx.peer, "끝" if sync_proc.returncode == 0 else f"실패({sync_proc.returncode}) {err[-1] if err else ''}")
            sync_proc = None
        if holder and now - last_sync >= sync_every and sync_proc is None:
            sync_proc, last_sync = ctx.rsync(CONF["COLLECTOR_DIR"], COLLECTOR_EXCLUDE), now
        write_status(ctx, collector_owner=ctx.me if holder else None, holder=holder, valkey=r is not None)
        if once:
            return holder
        for _ in range(check * 2):
            if stop["now"]:
                break
            time.sleep(0.5)
    # 감시를 멈추면(점검 · 재부팅) 수집기도 끄고 임대를 놓아 상대가 바로 이어받게
    ctx.set_unit("omm-collector", False)
    try:
        (r or valkey()).eval(RELEASE_LUA, 1, ctx.key, ctx.me)
    except Exception:
        pass
    log.warning("감시 끝: 수집기 끄고 임대 놓음")


def handover(ctx):
    r = valkey()
    r.set(ctx.pause_key, "1", ex=int(CONF["PAUSE"]))
    released = r.eval(RELEASE_LUA, 1, ctx.key, ctx.me)
    ctx.set_unit("omm-collector", False)
    print(f"{ctx.me}: 수집기 {'넘김' if released else '주인이 아니었음'} · {CONF['PAUSE']}초 동안 다시 안 잡음. "
          f"{ctx.peer} 는 약 {CONF['GRACE']}초 뒤 이어받음 (그 전에 rsync 한 번: omm_ha.py sync)")


# ── 노멀라이저 ────────────────────────────────────────────────────────────────
def collect_done_at():
    """오늘 수집 일일 작업이 끝난 시각 (collector daily_pipeline.sh 가 마지막에 daily_done.txt = 시작한 날짜). 아직이면 None
    주인이 아닌 서버에는 rsync(-a, 시각 유지)로 최대 SYNC 초 늦게 옴"""
    f = Path(CONF["COLLECTOR_DIR"]) / "data/raw/daily_done.txt"
    try:
        if f.read_text().strip() == time.strftime("%Y-%m-%d"):
            return f.stat().st_mtime
    except OSError:
        pass
    return None


def done_today(conn):
    """오늘 노멀라이저 성공 시각. 수집 일일 작업이 끝났으면 그 뒤의 성공만 (그 전 성공은 어제 수집분으로 돈 것)"""
    h, m = map(int, CONF["NORMALIZER_DAY_START"].split(":"))
    row = conn.execute("""SELECT max(finished_at) FROM omm_etl_runs WHERE job = 'mart_python_v4' AND status = 'ETL_OK'
                          AND finished_at >= greatest(current_date + make_interval(hours => %s, mins => %s),
                                                      to_timestamp(%s))""", (h, m, collect_done_at() or 0)).fetchone()
    return row[0]


def wait_collect(ctx):
    """수집 일일 작업이 끝날 때까지 기다림 (NORMALIZER_WAIT_UNTIL 까지). 잠금은 안 잡고 기다림 → 이 서버가 죽어도 다른 서버 backup 이 돌 수 있음"""
    h, m = map(int, CONF["NORMALIZER_WAIT_UNTIL"].split(":"))
    until = datetime.now().replace(hour=h, minute=m, second=0, microsecond=0).timestamp()
    poll = int(CONF["NORMALIZER_WAIT_POLL"])
    wkey = f"{ctx.key.rsplit(':', 1)[0]}:normalizer_wait"
    try:
        return _wait_collect(ctx, until, poll, wkey)
    finally:
        try:
            valkey().delete(wkey)            # 기다림 끝 → status 표시 지움
        except Exception:
            pass


def _wait_collect(ctx, until, poll, wkey):
    first = True
    while (t := collect_done_at()) is None:
        if time.time() >= until:
            if not first:
                log.warning("%s 까지 수집 일일 작업이 안 끝남 → 어제 수집분으로 노멀라이저 돌림 (수집이 끝나면 23:30 에 다시)", CONF["NORMALIZER_WAIT_UNTIL"])
            else:
                log.warning("수집 일일 작업이 오늘 안 끝남 (기다리는 시각 %s 지남) → 그냥 돌림", CONF["NORMALIZER_WAIT_UNTIL"])
            return False
        other = None
        try:                                 # status 에 보이게 (Valkey 안 되면 그냥 넘어감). 이미 다른 서버가 기다리는 중인지도 봄
            rv = valkey()
            other = rv.get(wkey)
            other = other.decode() if isinstance(other, bytes) else other
            rv.set(wkey, ctx.me, ex=poll + 120)
        except Exception:
            pass
        if first:
            log.warning("수집 일일 작업이 아직 안 끝남 → %s 까지 %d초마다 확인하며 기다림", CONF["NORMALIZER_WAIT_UNTIL"], poll)
            if other in (None, ctx.me):      # 두 서버가 같이 기다려도 알림은 한 번
                notify(ctx, "⏳", "노멀라이저가 수집을 기다림",
                       f"오늘 수집 일일 작업(18:00)이 아직 안 끝남 → 끝나면 바로 시작, {CONF['NORMALIZER_WAIT_UNTIL']} 까지 안 끝나면 어제 수집분으로 돌림")
            first = False
        time.sleep(max(1, min(poll, until - time.time())))
    if not first:
        log.warning("수집 일일 작업 끝남 (%s) → 노멀라이저 시작", datetime.fromtimestamp(t).strftime("%H:%M"))
        return "waited"
    return True


def normalizer(ctx, slot):
    """실패 · 예외는 슬랙으로 (DB 접속 실패 · 시간 초과 등)"""
    try:
        return _normalizer(ctx, slot)
    except Exception as e:
        log.exception("노멀라이저 오류")
        notify(ctx, "❌", "노멀라이저 오류로 못 돌림", f"`{type(e).__name__}: {str(e)[:200]}`\n{next_try()} · 로그 `sudo tail /var/log/omm-ha-normalizer.log`")
        raise


def next_try():
    hm = datetime.now().strftime("%H:%M")
    return "21:30 예비 실행이 다시 시도" if hm < "21:30" else ("23:30 예비 실행이 다시 시도" if hm < "23:30" else "오늘 자동 재시도 없음 → 손으로 다시 돌리기")


def _normalizer(ctx, slot):
    prefer = CONF["PREFER_NORMALIZER"]
    if slot == "main" and ctx.me != prefer:
        log.info("main 시간: 노멀라이저 우선 서버(%s)가 돌림 → 건너뜀", prefer)
        return 0
    with pg() as conn:
        if (t := done_today(conn)):
            log.info("오늘 노멀라이저 이미 성공 (%s) → 건너뜀", t)
            return 0
    wc = wait_collect(ctx)                   # DB 연결은 닫고 기다림 (오래 걸릴 수 있음). True 바로 · "waited" 기다림 · False 시각 넘김
    with pg() as conn:
        if (t := done_today(conn)):          # 기다리는 동안 다른 서버가 돌렸을 수 있음
            log.info("오늘 노멀라이저 이미 성공 (%s) → 건너뜀", t)
            return 0
        if not conn.execute("SELECT pg_try_advisory_lock(%s)", (PG_LOCK,)).fetchone()[0]:
            log.warning("다른 서버가 노멀라이저를 돌리는 중 → 건너뜀")
            return 0
        try:
            why = []                         # 평소(20:30 우선 서버 · 바로 시작)와 다른 점 → 있으면 결과를 슬랙으로
            if slot == "backup" and ctx.me != prefer:
                log.warning("%s 가 오늘 노멀라이저를 못 돌림 → %s 가 대신 돌림", prefer, ctx.me)
                why.append(f"{prefer} 대신 {ctx.me} 가 돌림")
            elif slot == "backup":
                why.append(f"{datetime.now():%H:%M} 예비 실행")
            if wc == "waited":
                why.append("수집 끝나길 기다린 뒤")
            elif wc is False:
                why.append("어제 수집분으로")
                notify(ctx, "⚠️", "수집이 안 끝나 어제 수집분으로 노멀라이저 돌림",
                       f"{CONF['NORMALIZER_WAIT_UNTIL']} 까지 오늘 수집 일일 작업이 안 끝남 → 수집이 나중에 끝나면 23:30 에 다시 돌림. 수집 로그 확인")
            log.warning("노멀라이저 시작 (%s, slot=%s)", ctx.me, slot)
            d = CONF["NORMALIZER_DIR"]
            # admina crontab 에 있던 그대로: 낮은 우선순위 · 메모리 조각 줄이기 (API 가 느려지지 않게)
            r = ctx.run(["runuser", "-u", CONF["NORMALIZER_USER"], "--", "nice", "-n", "10", "env", "MALLOC_ARENA_MAX=2",
                         f"{d}/daily.sh"], timeout=int(CONF["NORMALIZER_TIMEOUT"]))
            ok = r.returncode == 0 and (ctx.dry or done_today(conn))
            (log.warning if ok else log.error)("노멀라이저 %s (종료 코드 %s)", "성공" if ok else "실패", r.returncode)
            if ok:
                ctx.rsync(d, NORMALIZER_EXCLUDE, wait=True)
                if why:
                    notify(ctx, "✅", "노멀라이저 성공 (" + " · ".join(why) + ")")
            else:
                tail = [l.strip()[:200] for l in ((r.stdout or "") + "\n" + (r.stderr or "")).splitlines() if l.strip()][-3:]
                notify(ctx, "❌", f"노멀라이저 실패 (종료 코드 {r.returncode}{', ' + ' · '.join(why) if why else ''})",
                       ("```" + "\n".join(tail) + "```\n" if tail else "")
                       + f"{next_try()} · 로그 `sudo tail /var/log/omm-ha-normalizer.log` · `{d}/logs/daily_{datetime.now():%F}.log`")
            return 0 if ok else 1
        finally:
            conn.execute("SELECT pg_advisory_unlock(%s)", (PG_LOCK,))


def status(ctx):
    r = valkey()
    owner = r.get(ctx.key)
    ttl = r.pttl(ctx.key)
    info = {"나": ctx.me, "상대": ctx.peer, "수집기 주인": owner.decode() if isinstance(owner, bytes) else owner,
            "임대 남은 초": round(ttl / 1000, 1) if ttl and ttl > 0 else None,
            "이 서버 점검 중(pause)": bool(r.exists(ctx.pause_key)),
            "노멀라이저 수집 기다림": (lambda w: w.decode() if isinstance(w, bytes) else w)(r.get(f"{ctx.key.rsplit(':', 1)[0]}:normalizer_wait")),
            "오늘 수집 일일 작업": (lambda t: f"끝 {datetime.fromtimestamp(t):%H:%M}" if t else "아직")(collect_done_at()),
            **{u: ("켜짐" if subprocess.run(["systemctl", "is-active", "--quiet", u]).returncode == 0 else "꺼짐")
               for u in ("omm-ha", "omm-collector", "omm-sink", "omm-api")}}
    with pg() as conn:
        t = done_today(conn)
        info["오늘 노멀라이저"] = f"성공 {t:%H:%M}" if t else "아직"
        info["노멀라이저 실행 중"] = not conn.execute("SELECT pg_try_advisory_lock(%s)", (PG_LOCK,)).fetchone()[0]
        if not info["노멀라이저 실행 중"]:
            conn.execute("SELECT pg_advisory_unlock(%s)", (PG_LOCK,))
    for k, v in info.items():
        print(f"  {k:16} {v}")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("cmd", choices=["watch", "normalizer", "status", "handover", "sync"])
    p.add_argument("--slot", choices=["main", "backup"], default="main")
    p.add_argument("--normalizer", action="store_true", help="sync: 노멀라이저 폴더")
    p.add_argument("--me")
    p.add_argument("--prefix", default="omm:ha")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--once", action="store_true", help="watch: 한 번만")
    a = p.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s omm-ha %(levelname)s %(message)s", datefmt="%F %T")
    load_env()
    ctx = Ctx(a)
    if a.cmd == "watch":
        watch(ctx, once=a.once)
    elif a.cmd == "normalizer":
        sys.exit(normalizer(ctx, a.slot))
    elif a.cmd == "status":
        status(ctx)
    elif a.cmd == "handover":
        handover(ctx)
    elif a.cmd == "sync":
        ctx.rsync(CONF["NORMALIZER_DIR"] if a.normalizer else CONF["COLLECTOR_DIR"],
                  NORMALIZER_EXCLUDE if a.normalizer else COLLECTOR_EXCLUDE, wait=True)


if __name__ == "__main__":
    main()
