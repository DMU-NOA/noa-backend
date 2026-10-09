#!/usr/bin/env bash
# =====================================================================
# - 필수 도구(git, python3, venv)가 없으면 자동 설치
# - 최초 실행: clone, 가상환경 생성, systemd 서비스 등록까지 자동 처리
# - 이후 실행: 최신 코드로 갱신하고 서비스만 재시작
# =====================================================================

# set -e : 명령이 하나라도 실패하면 즉시 중단
# set -u : 정의되지 않은 변수를 쓰면 에러 처리
# set -o pipefail : 파이프(|) 중간 명령이 실패해도 에러 처리
set -euo pipefail

# ---------- 설정값 ----------
APP_DIR=/home/ec2-user/backend                      # 코드가 설치될 위치
REPO=https://github.com/DMU-NOA/noa-backend.git     # 퍼블릭 저장소 주소
ENV_FILE=/home/ec2-user/backend.env                 # API 키, DB 비밀번호 파일 (코드 폴더 밖)
SERVICE=backend                                     # systemd 서비스 이름
SHA="${1:-origin/main}"                             # 첫 번째 인자(커밋 SHA). 없으면 origin/main

# root 로 실행되면 sudo 불필요, 일반 사용자면 sudo 사용
if [ "$(id -u)" -eq 0 ]; then SUDO=""; else SUDO="sudo"; fi

# ---------- 0. 필수 도구 확인 및 자동 설치 ----------
# 패키지 관리자(dnf/yum/apt-get)를 자동으로 골라 설치
install_pkg() {
  if command -v dnf > /dev/null; then
    $SUDO dnf install -y "$@"            # Amazon Linux 2023
  elif command -v yum > /dev/null; then
    $SUDO yum install -y "$@"            # Amazon Linux 2
  elif command -v apt-get > /dev/null; then
    $SUDO apt-get update -y
    $SUDO apt-get install -y "$@"        # Ubuntu / Debian
  else
    echo "ERROR: 지원하지 않는 OS 입니다 (dnf/yum/apt-get 없음)."
    exit 1
  fi
}

# git, python3 가 없으면 설치
command -v git > /dev/null     || install_pkg git
command -v python3 > /dev/null || install_pkg python3

# python3 -m venv 가 안 되면 추가 설치 (Ubuntu 는 별도 패키지)
if ! python3 -m venv --help > /dev/null 2>&1; then
  if command -v apt-get > /dev/null; then
    install_pkg python3-venv python3-pip
  else
    install_pkg python3-pip
  fi
fi

# 설치 후에도 없으면 중단
for cmd in git python3; do
  command -v "$cmd" > /dev/null || { echo "ERROR: $cmd 설치 실패"; exit 1; }
done

# ---------- 1. 사전 점검 ----------
# 환경변수 파일이 없으면 서비스가 시작할 수 없으므로 먼저 중단
if [ ! -f "$ENV_FILE" ]; then
  echo "ERROR: $ENV_FILE 가 없습니다. EC2에서 먼저 작성하세요."
  exit 1
fi

# ---------- 2. 코드 받기 ----------
# 폴더가 아직 없으면(최초 배포) 저장소를 clone
if [ ! -d "$APP_DIR/.git" ]; then
  git clone "$REPO" "$APP_DIR"
fi

cd "$APP_DIR"

# 최신 내용을 가져온 뒤, push된 커밋과 정확히 같은 상태로 맞춤
git fetch origin main
git reset --hard "$SHA"

# ---------- 3. 파이썬 환경 ----------
# 가상환경이 없으면(최초 배포) 생성
[ -d venv ] || python3 -m venv venv

# requirements.txt 패키지를 가상환경에 설치 (이미 있는 건 건너뜀)
./venv/bin/pip install -r requirements.txt

# ---------- 4. systemd 서비스 등록 ----------
# 서비스 파일이 없으면(최초 배포) 새로 만듦
if [ ! -f "/etc/systemd/system/${SERVICE}.service" ]; then
  $SUDO tee "/etc/systemd/system/${SERVICE}.service" > /dev/null <<'EOF'
[Unit]
Description=NOA Backend (FastAPI)
After=network.target

[Service]
User=ec2-user
WorkingDirectory=/home/ec2-user/backend
# 환경변수 파일: OPENAI_API_KEY, DB 접속 정보 등
EnvironmentFile=/home/ec2-user/backend.env
# 서버 실행 명령 (0.0.0.0 = 외부에서 접근 가능)
ExecStart=/home/ec2-user/backend/venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
# 프로세스가 죽으면 3초 뒤 자동 재시작
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF
  $SUDO systemctl daemon-reload          # 새 서비스 파일 인식
  $SUDO systemctl enable "$SERVICE"      # EC2 재부팅 시 자동 시작
fi

# ---------- 5. 재시작 및 정상 기동 확인 ----------
$SUDO systemctl restart "$SERVICE"
sleep 3   # 서버가 완전히 뜰 때까지 잠깐 대기

# 실행 중이 아니면 최근 로그 30줄을 출력하고 실패 처리 (Actions 로그에서 원인 확인 가능)
$SUDO systemctl is-active --quiet "$SERVICE" || {
  $SUDO journalctl -u "$SERVICE" -n 30 --no-pager
  exit 1
}

echo "배포 완료: $SHA"