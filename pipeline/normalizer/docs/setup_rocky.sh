#!/usr/bin/env bash
# Rocky Linux (DB1) 최초 1회 설치 · 이 폴더(/opt/omm)에서 실행:  bash setup_rocky.sh
set -euo pipefail
cd "$(dirname "$(readlink -f "$0")")"
sudo dnf install -y python3 python3-pip cronie unzip
# PostgreSQL 은 이미 설치된 것을 그대로 씀. pg_trgm(contrib)만 같은 버전으로 맞춰 설치
if rpm -qa | grep -qE '^postgresql[0-9]+-server'; then                  # PGDG 저장소 (예: postgresql16-server)
  V=$(rpm -qa | grep -oE '^postgresql[0-9]+-server' | head -1 | grep -oE '[0-9]+')
  sudo dnf install -y "postgresql${V}-contrib" || echo "  contrib 설치 실패 → DBA에게 pg_trgm 확인 요청"
  command -v psql >/dev/null || sudo ln -sf "/usr/pgsql-${V}/bin/psql" /usr/local/bin/psql
elif rpm -q postgresql-server >/dev/null 2>&1; then                     # Rocky 기본 저장소
  sudo dnf install -y postgresql-contrib
else
  echo "  이 서버에는 PostgreSQL 서버가 없어요 (DB1 이 맞는지 확인). psql 클라이언트만 설치합니다."
  sudo dnf install -y postgresql
fi
sudo dnf install -y google-noto-sans-cjk-ttc-fonts 2>/dev/null || sudo dnf install -y google-noto-sans-cjk-fonts 2>/dev/null || echo "한글 글꼴 설치 실패 (차트 한글만 깨짐 · 나머지는 정상)"
sudo systemctl enable --now crond
sudo timedatectl set-timezone Asia/Seoul
python3 -m venv .venv
./.venv/bin/pip install --upgrade pip -q
./.venv/bin/pip install -q pandas scikit-learn networkx psycopg2-binary pymongo requests matplotlib playwright
# 크롤링용 크롬(headless)과 필요한 라이브러리 (Rocky 는 playwright install-deps 를 지원하지 않아서 직접 설치)
for p in nss nspr atk at-spi2-atk cups-libs libdrm libxkbcommon libXcomposite libXdamage libXext libXfixes libXrandr \
         mesa-libgbm pango cairo alsa-lib libxshmfence liberation-fonts; do sudo dnf install -y -q "$p" >/dev/null 2>&1 || echo "  (건너뜀: $p)"; done
./.venv/bin/python -m playwright install chromium
mkdir -p data/mangae data/kamis_out data/youtube logs
[ -f omm.env ] || { cp omm.env.example omm.env; echo "→ omm.env 를 열어 키와 비밀번호를 넣으세요: vi omm.env"; }
chmod 600 omm.env omm.env.example
chmod +x run_all.sh daily.sh crawl.sh status.sh
sed -i 's/\r$//' *.sh *.py *.sql omm.env* 2>/dev/null || true      # Windows 에서 복사한 줄바꿈(CRLF) 정리
echo "설치 끝. 다음: omm.env 값 넣기 → DB 준비 → crontab 등록 (README_VM.md)"
