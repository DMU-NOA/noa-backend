#!/usr/bin/env bash
# =====================================================================
# - 처음 실행: 코드 clone, 가상환경 생성, 서비스 등록까지 자동 처리
# - 이후 실행: 최신 코드로 갱신하고 서비스만 재시작
# =====================================================================

# set -e : 명령이 하나라도 실패하면 즉시 중단 (실패한 채로 재시작되는 것 방지)
# set -u : 정의되지 않은 변수를 쓰면 에러 처리 (오타 방지)
# set -o pipefail : 파이프(|) 중간 명령이 실패해도 에러로 처리
set -euo pipefail

# ---------- 설정값 ----------
APP_DIR=/home/ec2-user/backend                      # 코드가 설치될 위치
REPO=https://github.com/DMU-NOA/noa-backend.git     # 퍼블릭 저장소 주소
ENV_FILE=/home/ec2-user/backend.env                 # API 키, DB 비밀번호가 든 파일 (코드 폴더 밖)
SHA="${1:-origin/main}"                             # 첫 번째 인자(커밋 SHA). 없으면 origin/main

# ---------- 사전 점검 ----------
# .env 가 없으면 서비스가 시작할 수 없으므로 먼저 알려주고 중단
if [ ! -f "$ENV_FILE" ]; then
  echo "ERROR: $ENV_FILE 가 없습니다. EC2에서 먼저 작성하세요."
  exit 1
fi

# ---------- 1. 코드 받기 ----------
# 폴더가 아직 없으면(최초 배포) 저장소를 clone
if [ ! -d "$APP_DIR/.git" ]; then
  git clone "$REPO" "$APP_DIR"
fi

cd "$APP_DIR"

# GitHub에서 최신 내용을 가져온 뒤, push된 커밋과 정확히 같은 상태로 맞춤
git fetch origin main
git reset --hard "$SHA"

# ---------- 2. 파이썬 환경 ----------
# 가상환경(venv)이 없으면(최초 배포) 생성
[ -d venv ] || python3 -m venv venv

# requirements.txt 의 패키지를 가상환경에 설치 (이미 있는 건 건너뜀)
./venv/bin/pip install -r requirements.txt

# ---------- 3. systemd 서비스 등록 ----------
# 서비스 파일이 없으면(최초 배포) 새로 만듦
# systemd 는 "서버가 꺼져도 자동 재시작, 죽으면 다시 실행" 을 해주는 리눅스 서비스 관리자
if [ ! -f /etc/systemd/system/backend.service ]; then
  sudo tee /etc/systemd/system/backend.service > /dev/null <<'EOF'
[Unit]
Description=NOA Backend (FastAPI)
After=network.target

[Service]
User=ec2-user
WorkingDirectory=/home/ec2-user/backend
# 환경변수 파일: OPENAI_API_KEY, DB 접속 정보 등을 여기서 읽음
EnvironmentFile=/home/ec2-user/backend.env
# 서버 실행 명령 (0.0.0.0 = 외부에서 접근 가능)
ExecStart=/home/ec2-user/backend/venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
# 프로세스가 죽으면 3초 뒤 자동 재시작
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF
  sudo systemctl daemon-reload     # systemd 가 새 서비스 파일을 인식하게 함
  sudo systemctl enable backend    # EC2 재부팅 시 자동 시작되도록 등록
fi

# ---------- 4. 서비스 재시작 ----------
# 새 코드로 서버를 다시 띄움
sudo systemctl restart backend
sleep 3   # 서버가 완전히 뜰 때까지 잠깐 대기

# ---------- 5. 정상 기동 확인 ----------
# 서비스가 실행 중이 아니면 최근 로그 30줄을 출력하고 실패 처리
# (Actions 로그에서 바로 원인을 볼 수 있음)
sudo systemctl is-active --quiet backend || {
  sudo journalctl -u backend -n 30 --no-pager
  exit 1
}

echo "배포 완료: $SHA"