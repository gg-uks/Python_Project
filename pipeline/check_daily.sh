#!/bin/bash
# OMM 매일 점검: 수집(18:00) · 정제(20:30) · 서비스 · 데이터 수 · API  — back1 · back2 이중화 대응 (11/26)
# 사용: bash /opt/pipeline/check_daily.sh [날짜] [--slack] [--preview] [--if-owner]
#   날짜 기본 오늘 (예: 2026-11-26)
#   --slack     결과를 슬랙으로도 보냄 (/opt/pipeline/slack.env 의 SLACK_WEBHOOK_URL) — 항목별 한 줄 요약, 문제 있는 항목만 원문 덧붙임
#   --preview   슬랙에 보낼 내용을 보내지 않고 화면에만 (모양 확인용)
#   --if-owner  이 서버가 지금 수집기 주인일 때만 점검 (두 서버 cron 에 같이 넣어도 슬랙은 한 번만 감)
# 이중화 뒤 바뀐 점
#   - 수집기는 주인 서버(평소 back1)에서만 켜져 있음 → 주인이 아닌 서버에서 꺼져 있는 건 정상
#   - 노멀라이저는 평소 back2 가 돌림 → 성공 여부는 DB(omm_etl_runs)로 판단, 로그는 상대 서버에 있으면 가져와서 봄
#   - 11-27~: 노멀라이저는 수집 일일 작업이 끝난 뒤에 돎 (안 끝났으면 22:30 까지 기다림) → 수집이 끝난 뒤의 성공만 [OK]
#   - root(sudo · /etc/cron.d)로 돌려야 수집기 주인 확인 · 상대 서버 로그 가져오기가 됨. 아니면 back1 을 주인으로 가정
D=$(date +%F); SLACK=0; IFOWNER=0; PREVIEW=0
for a in "$@"; do
  case "$a" in
    --slack) SLACK=1 ;;
    --preview) PREVIEW=1 ;;
    --if-owner) IFOWNER=1 ;;
    20[0-9][0-9]-*) D=$a ;;
  esac
done
C=/opt/pipeline/collector
N=/opt/pipeline/normalizer
HA=/opt/pipeline/ha
ok()   { echo "  [OK]  $*"; }
bad()  { echo "  [!!]  $*"; }
info() { echo "  [..]  $*"; }
sum()  { echo "@@ $*"; }       # 슬랙 한 줄 요약 (화면에는 안 보임)

ME=$(hostname -s | tr 'A-Z' 'a-z')
case "$ME" in back1) PEER=back2 ;; back2) PEER=back1 ;; *) PEER= ;; esac
TODAY=0; [ "$D" = "$(date +%F)" ] && TODAY=1
NOW=$(date +%H%M)

# 수집기 주인 · 노멀라이저 실행 중 (omm-ha 임대, root 만 읽힘)
HA_ST=$(/opt/pipeline/api/.venv/bin/python -I $HA/omm_ha.py status 2>/dev/null)
OWNER=$(awk '$1=="수집기" && $2=="주인" {print $3}' <<< "$HA_ST")
NRUN=$(awk '$1=="노멀라이저" && $2=="실행" {print $4}' <<< "$HA_ST")
NWAIT=$(awk '$1=="노멀라이저" && $2=="수집" && $3=="기다림" {print $4}' <<< "$HA_ST")   # 수집 일일 작업 끝나길 기다리는 서버 (11-27~)
OWNER_NOTE=""
if [ -z "$OWNER" ] || [ "$OWNER" = None ]; then
  OWNER=back1; OWNER_NOTE=" (확인 못 함 → back1 로 가정. root 로 돌리면 정확)"
fi

if [ "$IFOWNER" = 1 ] && [ "$ME" != "$OWNER" ]; then
  echo "$(date '+%F %T') 수집기 주인이 $OWNER → 이 서버($ME)는 점검 · 슬랙 안 함"; exit 0
fi

TMP=$(mktemp -d); trap 'rm -rf "$TMP"' EXIT
peer_get() {   # 상대 서버 /opt/pipeline/<경로> 파일 가져오기 (omm-ha rsync 키 · root 만)
  [ -n "$PEER" ] && [ -r $HA/sync_key ] || return 1
  rsync -q -t --timeout=20 -e "ssh -i $HA/sync_key -o BatchMode=yes -o ConnectTimeout=5 -o StrictHostKeyChecking=accept-new -o UserKnownHostsFile=$HA/known_hosts" \
    "ommsync@$PEER:$1" "$TMP/" 2>/dev/null && [ -f "$TMP/$(basename "$1")" ]
}

main() {
echo "===== OMM 점검 $D ($(date '+%H:%M')) · 점검 서버 $ME · 수집기 주인 $OWNER$OWNER_NOTE ====="

echo "1. 서비스 ($ME)"
for s in omm-sink omm-api omm-ha; do
  [ "$(systemctl is-active $s)" = active ] && ok "$s" || bad "$s 꺼져 있음"
done
non=0; for s in omm-sink omm-api omm-ha; do [ "$(systemctl is-active $s)" = active ] && non=$((non+1)); done
col=$(systemctl is-active omm-collector)
if [ "$ME" = "$OWNER" ]; then
  [ "$col" = active ] && ok "omm-collector (이 서버가 주인)" || bad "omm-collector 꺼져 있음 (이 서버가 주인인데)"
else
  [ "$col" = active ] && bad "omm-collector 가 주인($OWNER)이 아닌데 켜져 있음 → 두 대가 같이 수집 중일 수 있음" || ok "omm-collector 대기 (주인 $OWNER)"
fi
if [ -n "$PEER" ]; then
  code=$(curl -s -m 5 -o /dev/null -w '%{http_code}' http://$PEER:8000/api/health)
  [ "$code" = 200 ] && ok "$PEER API 응답 200" || bad "$PEER API 응답 없음 ($code) → 한 대로만 서비스 중"
fi
sum "$ME 서비스 $non/3 켜짐 · 수집기 $([ "$col" = active ] && echo 켜짐 || echo 대기)${PEER:+ · $PEER API $code}"

echo "2. 수집 18:00 (collector logs/daily_$D.log)"
L=$C/logs/daily_$D.log; WHERE=$ME
if [ ! -f "$L" ] && peer_get "collector/logs/daily_$D.log"; then L=$TMP/daily_$D.log; WHERE=$PEER; fi
if [ -f "$L" ]; then
  echo "        파일: $WHERE"
  grep -q '!!!!!' "$L" && bad "실패한 단계 있음:" && grep '!!!!!' "$L" | sed 's/^/        /'
  grep -q '=====.* 끝 =====' "$L" && ok "끝까지 돎 ($(grep '=====.* 끝 =====' "$L" | grep -o '[0-9:]\{8\}'))" || bad "끝 표시 없음 (아직 도는 중이거나 멈춤)"
  ET=$(grep '=====.* 끝 =====' "$L" | tail -1 | grep -o '[0-9]\{2\}:[0-9]\{2\}' | head -1)
  NF=$(grep -c '!!!!!' "$L")
  KN=$(awk '/\[OMM_kamis_prices_raw\]/{f=1} f&&/끝:/{match($0,/새로 [0-9,]+/); print substr($0,RSTART+3,RLENGTH-3); exit}' "$L")
  sum "$([ -n "$ET" ] && echo "$ET 끝" || echo "끝 표시 없음") ($WHERE)${KN:+ · KAMIS 새로 $KN}$([ "$NF" -gt 0 ] && echo " · 실패 단계 $NF개")"
  grep -e '캐시 .*개 중' -e '이미 넣은 CSV' -e '^\[OMM_' -e '끝:' "$L" | sed 's/^/        /'
else
  [ "$TODAY" = 1 ] && [ "$NOW" -lt 1800 ] && info "아직 18:00 전" || bad "로그 없음 ($ME${PEER:+ · $PEER} 모두) → 매일 작업이 안 돌았음"
  [ "$TODAY" = 1 ] && [ "$NOW" -lt 1800 ] && sum "아직 18:00 전" || sum "로그 없음"
fi

echo "3. 유튜브 (몽고 OMM_youtube_videos · run_date $D)"
# YouTube API → trend_videos.csv → 카프카 → omm-sink → 몽고 까지 다 왔는지 (몽고에 그날 회차가 있으면 끝까지 온 것)
( cd $C && TODAY=$TODAY NOW=$NOW LOGF="$L" /opt/pipeline/venv/bin/python - "$D" <<'PYEOF' 2>&1 | grep -v '^접속'
import sys, os, re, csv, datetime; sys.path.insert(0, 'load'); import load_mongo as L, paths as P
D = sys.argv[1]; prev = str(datetime.date.fromisoformat(D) - datetime.timedelta(days=1))
c = L.connect()['OMM_youtube_videos']
def day(d):
    r = list(c.aggregate([{'$match': {'run_date': d}},
                          {'$group': {'_id': None, 'n': {'$sum': 1}, 'v': {'$addToSet': '$video_id'}, 'q': {'$addToSet': '$query'}}}]))
    return (r[0]['n'], len(r[0]['v']), len(r[0]['q'])) if r else (0, 0, 0)
n, v, q = day(D); pn = day(prev)[0]
qn = sum(1 for row in csv.DictReader(open(os.path.join(P.DICT, 'youtube_queries.csv'), encoding='utf-8-sig')) if row.get('query', '').strip())
lf = os.environ.get('LOGF', '')
log = open(lf, encoding='utf-8', errors='replace').read() if os.path.isfile(lf) else ''
m = re.search(r'=====[^\n]*youtube_trend.*?(?=\n=====|\Z)', log, re.S); yl = m.group(0) if m else ''
sent = re.search(r'\[카프카\] 보냄 ([0-9,]+)건 · 실패 ([0-9,]+)건', yl)
num = lambda s: int(s.replace(',', ''))
if n == 0:
    early = os.environ.get('TODAY') == '1' and int(os.environ.get('NOW', '0')) < 1830
    print(f"  [{'..' if early else '!!'}]  {'아직 18:00 일일 작업 전' if early else '그날 회차가 몽고에 없음 → 수집 로그의 youtube_trend 단계 확인'}")
    print('@@ ' + ('아직 18:00 일일 작업 전' if early else '수집 없음'))
else:
    bad = []
    if q < qn: bad.append(f'검색어 {q}/{qn}개만 수집 (할당량 초과?)')
    if pn and n < pn * 0.7: bad.append(f'어제보다 크게 줄었음 ({pn:,} → {n:,})')
    if sent and num(sent.group(2)): bad.append(f'카프카 전송 실패 {sent.group(2)}건')
    if sent and n < num(sent.group(1)): bad.append(f'카프카로 {sent.group(1)}건 보냈는데 몽고에 {n:,}건 (싱크 확인)')
    for b in bad: print(f'  [!!]  {b}')
    if not bad: print(f'  [OK]  {n:,}건 · 영상 {v:,}개 · 검색어 {q}/{qn}' + (f' · 카프카 {sent.group(1)}건 = 몽고' if sent else ''))
    print(f"@@ {n:,}건 (영상 {v:,} · 검색어 {q}/{qn})" + (f" · 어제 {pn:,}" if pn else ''))
if '할당량을 다 썼어요' in yl: print('  [!!]  YouTube API 하루 할당량 초과 (로그)')
PYEOF
)

echo "4. 정제 20:30 (DB omm_etl_runs + daily_$D.log)"
# 수집 일일 작업이 끝난 뒤의 성공만 (그 전 성공은 어제 수집분으로 돈 것) — 끝 시각 = collector data/raw/daily_done.txt 수정 시각
CD=; DF=$C/data/raw/daily_done.txt
[ "$(cat $DF 2>/dev/null)" = "$D" ] && CD=$(stat -c %Y $DF)
NT=$(cd $N && set -a && . ./omm.env && set +a
  psql -X -At -c "SELECT coalesce(to_char(max(finished_at), 'HH24:MI'), '-') FROM omm_etl_runs
                  WHERE job = 'mart_python_v4' AND status = 'ETL_OK'
                    AND finished_at >= greatest('$D'::date + time '12:00', to_timestamp(${CD:-0})) AND finished_at < '$D'::date + 1" 2>&1)
if [[ "$NT" =~ ^[0-9]{2}:[0-9]{2}$ ]]; then
  ok "성공 $NT (omm_etl_runs ETL_OK${CD:+, 수집 끝 $(date -d @$CD +%H:%M) 뒤})"; sum "$NT 성공"
elif [ "$NT" != - ]; then
  bad "DB 확인 실패: $(head -1 <<< "$NT")"; sum "DB 확인 실패"
elif [ "$NRUN" = True ]; then
  info "지금 도는 중"; sum "도는 중"
elif [ -n "$NWAIT" ] && [ "$NWAIT" != None ]; then
  info "$NWAIT 가 수집 일일 작업 끝나길 기다리는 중 (22:30 까지, 넘으면 그냥 돌림)"; sum "$NWAIT 가 수집 끝나길 기다리는 중"
elif [ "$TODAY" = 1 ] && [ "$NOW" -lt 2030 ]; then
  info "아직 20:30 전"; sum "아직 20:30 전"
elif [ "$TODAY" = 1 ] && [ "$NOW" -lt 2140 ]; then
  info "아직 성공 기록 없음 (21:30 에 살아 있는 서버가 대신 돌림)"; sum "아직 (21:30 에 대신 돌림)"
else
  bad "오늘 성공 기록 없음 → sudo tail /var/log/omm-ha-normalizer.log (back1 · back2)"; sum "성공 기록 없음"
fi
NL=$N/logs/daily_$D.log; WHERE=$ME
if [ ! -f "$NL" ] && peer_get "normalizer/logs/daily_$D.log"; then NL=$TMP/daily_$D.log; WHERE=$PEER; fi
if [ -f "$NL" ]; then
  echo "        로그: $WHERE ($(date -r "$NL" '+%m-%d %H:%M'))"
  tail -n 3 "$NL" | grep -q '끝' || info "로그 마지막에 '끝'이 없음"
  grep -i -E 'error|traceback|실패' "$NL" | tail -3 | sed 's/^/        /'
  grep '반영 후 문서 수' "$NL" | tail -4 | sed 's/^/        ES /'
else
  echo "        로그: 이 서버에 없음${PEER:+ (상대 $PEER 에 있을 수 있음, root 로 돌리면 가져옴)}"
fi

echo "5. 싱크·수집기 오류 ($ME 저널)"
ES=""
for s in omm-sink omm-collector; do
  n=$(journalctl -u $s --since "$D 00:00" --until "$D 23:59:59" --no-pager 2>/dev/null | grep -c -i -E 'error|exception|traceback')
  [ "$n" -eq 0 ] && ok "$s 오류 0건" || bad "$s 오류 $n건 → journalctl -u $s --since '$D'"
  ES="$ES${ES:+ · }$([ $s = omm-sink ] && echo 싱크 || echo 수집기) $n건"
done
sum "$ES"

echo "6. 몽고 · 원본 건수"
( cd $C && /opt/pipeline/venv/bin/python - <<'EOF' 2>&1 | grep -v '^접속'
import sys, os, time; sys.path.insert(0, 'load'); import load_mongo as L, paths as P
db = L.connect()
n = sum(1 for l in open(P.RECIPES_JSONL, encoding='utf-8') if l.strip())
m = db['OMM_mangae_recipes_raw'].estimated_document_count()
print(f"  [{'OK' if abs(n - m) <= 50 else '!!'}]  레시피 원본 {n:,} · 몽고 {m:,}")
cnt = {}
for c in ['OMM_mangae_reviews_raw', 'OMM_kamis_prices_raw', 'OMM_youtube_videos', 'OMM_chamgagyeok_raw']:
    cnt[c] = db[c].estimated_document_count()
    print(f"        {c}: {cnt[c]:,}")
print(f"@@ 레시피 {m:,}{'' if abs(n - m) <= 50 else f' (원본 {n:,})'} · 후기 {cnt['OMM_mangae_reviews_raw']:,} · 유튜브 {cnt['OMM_youtube_videos']:,} · KAMIS {cnt['OMM_kamis_prices_raw']/1e6:.1f}백만")
st = os.path.join(os.path.dirname(P.KAMIS_CACHE), '.kamis_loaded_at')
if os.path.exists(st):
    print('        KAMIS 마지막 적재 시작:', time.strftime('%m-%d %H:%M', time.localtime(float(open(st).read()))))
EOF
)

echo "7. PG 이번 달 평년값"
PV=$(cd $N && set -a && . ./omm.env && set +a
  psql -X -P pager=off -At -F' · ' -c "SELECT market_type, count(*)||'행', round(100.0*count(normal_price)/count(*),1)||'% 평년있음'
    FROM omm_price_monthly WHERE ym = date_trunc('month', now())::date GROUP BY 1 ORDER BY 1" 2>&1)
sed 's/^/        /' <<< "$PV"
if grep -q '% 평년있음' <<< "$PV"; then
  sum "$(awk -F' · ' '/% 평년있음/{sub(/MARKET_RETAIL/,"소매",$1); sub(/MARKET_WHOLESALE/,"도매",$1); sub(/ 평년있음/,"",$3); printf "%s%s %s", (NR>1?" · ":""), $1, $3}' <<< "$PV")"
else
  bad "이번 달 평년값 없음"; sum "이번 달 값 없음"
fi

echo "8. API ($ME)"
curl -s -m 10 localhost:8000/api/main | python3 -c "
import sys,json
m=json.load(sys.stdin).get('priceMovers') or {}
print('  [OK]' if any(m.values()) else '  [!!]', ' priceMovers', {k:[x['name'] for x in v] for k,v in m.items()})
f=lambda k: (m.get(k) or [{}])[0].get('name', '-')
print(f\"@@ 가격 변동 ↑{f('up')} ↓{f('down')}\")" 2>&1
curl -s -m 10 localhost:8000/api/analysis/price-interest | python3 -c "
import sys,json
d=json.load(sys.stdin); n=d.get('n',0)
print('  [OK]' if n else '  [!!]', f\" price-interest {d.get('ym')} 재료 {n}개 · r={d.get('r')}\")
print(f'@@ 가격-관심 재료 {n}개')" 2>&1

echo "9. 서버 자원 ($ME)"
free -m | awk '/Mem:/{printf "        메모리 남음 %dMB / %dMB\n", $7, $2}'
df -h / | awk 'NR==2{printf "        디스크 %s 사용 (남음 %s)\n", $5, $4}'
DU=$(df --output=pcent / | tail -1 | tr -dc 0-9)
[ "$DU" -ge 90 ] && bad "디스크 $DU% — 정리 필요"
[ "$DU" -ge 80 ] && [ "$DU" -lt 90 ] && info "디스크 $DU% — 곧 정리 필요"
sum "$(free -m | awk '/Mem:/{printf "메모리 %.1fG 남음", $7/1024}') · 디스크 $DU% ($(df -h --output=avail / | tail -1 | tr -d ' ') 남음)"
}

OUT=$(main 2>&1)
grep -v '^@@ ' <<< "$OUT"

# 슬랙 메시지: 항목별 한 줄 (✅ 정상 · ⏳ 아직/진행 중 · ❌ 확인 필요), 문제 있는 항목만 원문을 덧붙임
slack_payload() {
  printf '%s' "$OUT" | python3 -c '
import sys, re, json, datetime
D, ME, OWNER, NOTE, NOW = sys.argv[1:6]
out = sys.stdin.read()
names = {"1": "서비스", "2": "수집 18:00", "3": "유튜브", "4": "정제 20:30", "5": "오류 로그", "6": "원본 데이터", "7": "평년값", "8": "API", "9": "서버 자원"}
secs, cur = [], None
for line in out.splitlines():
    m = re.match(r"(\d)\. ", line)
    if m:
        cur = {"n": m.group(1), "raw": [line], "sum": [], "bad": [], "wait": []}; secs.append(cur); continue
    if cur is None: continue
    if line.startswith("@@ "): cur["sum"].append(line[3:]); continue
    cur["raw"].append(line)
    if "[!!]" in line: cur["bad"].append(line.split("[!!]", 1)[1].strip())
    elif "[..]" in line: cur["wait"].append(line.split("[..]", 1)[1].strip())
nbad = sum(len(s["bad"]) for s in secs)
day = datetime.date.fromisoformat(D); wd = "월화수목금토일"[day.weekday()]
title = (f"🟢 OMM 매일 점검 {day:%m/%d}({wd}) — 모두 정상" if nbad == 0 else f"🔴 OMM 매일 점검 {day:%m/%d}({wd}) — 확인 필요 {nbad}건")
lines = []
for s in secs:
    icon = "❌" if s["bad"] else ("⏳" if s["wait"] else "✅")
    txt = " · ".join(s["sum"]) or "-"
    w = s["wait"][0] if s["wait"] else ""
    if w and not s["bad"] and w not in txt and txt not in w: txt += f"  _({w})_"
    lines.append(f"{icon} *{names.get(s["n"], s["n"])}*   {txt}")
blocks = [{"type": "header", "text": {"type": "plain_text", "text": title}},
          {"type": "context", "elements": [{"type": "mrkdwn", "text": f"점검 {ME} · 수집기 주인 {OWNER}{NOTE} · {NOW}"}]}]
if nbad:
    todo = "\n".join(f"• *{names.get(s["n"], s["n"])}* — {b}" for s in secs for b in s["bad"])
    blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": "*확인할 것*\n" + todo}})
blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": "\n".join(lines)}})
if nbad:
    raw = "\n\n".join("\n".join(s["raw"]) for s in secs if s["bad"])
    blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": "```" + raw[:2800] + "```"}})
blocks.append({"type": "context", "elements": [{"type": "mrkdwn", "text": "자세히: `sudo bash /opt/pipeline/check_daily.sh`"}]})
if "--text" in sys.argv:
    print(title); print(blocks[1]["elements"][0]["text"]); print()
    for b in blocks[2:]: print(b["text"]["text"] if "text" in b else b["elements"][0]["text"]); print()
else:
    print(json.dumps({"text": title, "blocks": blocks}, ensure_ascii=False))
' "$D" "$ME" "$OWNER" "$OWNER_NOTE" "$(date '+%H:%M')" "$@"
}

if [ "$PREVIEW" = 1 ]; then
  echo; echo "──────── 슬랙 미리보기 (안 보냄) ────────"; slack_payload --text
fi
if [ "$SLACK" = 1 ]; then
  [ -f /opt/pipeline/slack.env ] && . /opt/pipeline/slack.env
  if [ -z "$SLACK_WEBHOOK_URL" ]; then
    echo "슬랙: /opt/pipeline/slack.env 에 SLACK_WEBHOOK_URL 이 없어서 안 보냄"; exit 0
  fi
  HEAD=$(slack_payload --text | head -1)
  R=$(slack_payload | curl -s -m 10 -X POST -H 'Content-type: application/json; charset=utf-8' --data-binary @- "$SLACK_WEBHOOK_URL")
  [ "$R" = ok ] && echo "슬랙: 보냄 ($HEAD)" || echo "슬랙: 보내기 실패 ($R)"
fi
