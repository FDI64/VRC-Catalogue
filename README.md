# VRC-Catalogue (VRCatalogue Restoration Project)

> **서비스 종료된 VRChat 전용 BOOTH 에셋 검색 엔진 'VRCatalogue'의 복원 및 개인용 자립형 웹 서비스 프로젝트**

[![Python Version](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100%2B-009688.svg)](https://fastapi.tiangolo.com/)
[![SQLite](https://img.shields.io/badge/SQLite-3-003B57.svg)](https://www.sqlite.org/)
[![Vue 3](https://img.shields.io/badge/Vue.js-3.x-4FC08D.svg)](https://vuejs.org/)
[![TailwindCSS](https://img.shields.io/badge/TailwindCSS-3.x-38B2AC.svg)](https://tailwindcss.com/)
[![License: CC BY 4.0](https://img.shields.io/badge/License-CC_BY_4.0-lightgrey.svg)](https://creativecommons.org/licenses/by/4.0/)

---

## 📖 1. 프로젝트 소개

**VRC-Catalogue (VRCatalogue Restoration Project)**는 2026년 10월 서비스를 종료하며 커뮤니티에 공개된 **VRCatalogue의 오픈 데이터셋(약 21.6만 개 메타데이터)**을 기반으로, 개인 로컬 환경에서 독립적으로 구동할 수 있도록 재설계된 **개인용 VRChat 애셋 아카이브 및 탐색 웹 서버**입니다.

원본 데이터셋의 가벼운 RDB 구조(아바타-의상 호환성, 태그, 카테고리 매핑)를 유지하면서, 저작권/용량 문제로 누락되었던 **상품 제목, 고화질 썸네일, 실제 가격 바리에이션**을 BOOTH 웹페이지에서 실시간으로 긁어와 로컬 캐싱하는 **하이브리드 온디맨드 아키텍처**를 채택했습니다.

---

## ✨ 2. 핵심 기능

### ⚡ 초고속 로컬 RDB 탐색 & 하이브리드 캐싱
* **21만 6천 개**의 VRChat BOOTH 아이템과 **380종**의 베이스 아바타 호환성 매핑 데이터를 로컬 SQLite로 0.01초 만에 쿼리합니다.
* 제목과 썸네일 이미지는 첫 조회 시 백그라운드 병렬 비동기(`httpx`)로 BOOTH에서 가져오며, 즉시 로컬 캐시 DB(`item_cache`)에 영구 보관되어 재방문 시 즉각 로딩됩니다.
* 판매자가 상품을 비공개/삭제(404) 처리한 경우 자동으로 감지하여 에러 없이 예외 처리합니다.

### 🎨 쇼핑몰 특화 UI / UX (4x3 대형 뷰어 & 고정 사이드바)
* **Sticky 사이드바**: 아무리 스크롤을 내려도 검색창, 아바타 선택, 카테고리, 태그 필터가 좌측에 고정되어 항상 조작 가능합니다.
* **4x3 대형 그리드**: 데스크톱 환경에 최적화된 4열 레이아웃으로 썸네일과 의상 디테일을 선명하고 큼직하게 렌더링합니다.
* **서브아이템 가격 감지 (`~` 물결표)**: 무료 체험판(0엔)과 풀팩 유료 버전이 공존하는 BOOTH 상품 특성을 감지하여, 최저가 옵션일 경우 `~¥500`, `~무료` 형태로 최저가 뱃지를 자동 부여합니다.
* **카테고리 뱃지**: `의상 · 원피스`, `헤어스타일`, `액세서리` 등 대분류/소분류를 카드 상단에 명시합니다.

### 🔍 다채로운 검색 & 다중 태그 포함/제외 필터
* **텍스트 검색**: 샵(제작자) 이름 및 제목 실시간 검색.
* **다중 태그 필터링**:
  * 12만 개 BOOTH 태그 및 한/영/일 정규화 태그 실시간 자동완성 검색.
  * **포함(`+`)** 및 **제외(`-`)** 모드를 원클릭으로 지정하여 정밀한 의상 탐색 가능 (예: `+안경`, `-비키니`).
  * 뱃지 클릭 시 포함 ➔ 제외 즉시 토글.

### 📈 트렌딩 및 스마트 정렬
* **🔥 좋아요순**: 누적 인기 순위 정렬.
* **⚡ 트렌딩 급상승**: 출시 기간 대비 좋아요 수집 속도를 수학적 중력 공식(Gravity Algorithm)으로 계산하여 최근 화제가 된 신작 우선 노출.
* **🕒 최신 등록순**: 제작자가 실제로 업로드한 원본 일시(`YY.MM.DD`) 기준 정렬.
* **💵 가격순**: 무료(0엔) 우선 및 고가 풀팩 순 정렬.

### 🌐 스마트 한국어 번역 & 핫로딩 (In-Place Hot-Reload)
* **NFKC 유니코드 복원**: 제작자가 멋으로 쓴 특수 수학 폰트(예: `𝑵𝒐𝒊𝒓_𝑳𝒖𝒙𝒆`)를 표준 영문(`Noir_Luxe`)으로 자동 정규화하여 글자가 증발하는 현상을 100% 방지.
* **영문 원문 보존**: 일본어가 전혀 없는 순수 영문 브랜드명(`Urban Tech Obsidian` 등)은 어색한 직역 없이 영문 원문 그대로 보존.
* **핫로딩 스위치**: 번역 기능을 켜고 끌 때 페이지가 튕기거나 스크롤이 리셋되지 않고, **보고 있던 화면 그 자리 그대로 문자열만 0초 만에 실시간 교체**.
* **양방향 툴팁**: 번역 모드에서는 일본어 원문을, 원문 모드에서는 한국어 번역본을 마우스 호버 시 툴팁으로 제공.

### 🤖 신규 에셋 자동 수집 파이프라인 (Crawler)
* BOOTH의 `#VRChat` 최신 피드를 5개 동시 병렬로 고속 탐색하여 DB에 없는 최신 신작을 발굴.
* 380개 베이스 아바타 이름 정규식 매칭, Modular Avatar(MA) 지원 여부, 셰이더(lilToon/Poiyomi) 키워드를 자동 분석하여 DB에 인덱싱.
* **가동 제어**: 서버 시작 시 백그라운드 1회 자동 점검 + UI 내 수동 동기화 버튼(안전 확인 모달창 연동).

### 🔒 로컬 암호화 기반 보안 시스템
* **PBKDF2-HMAC-SHA256**: 무작위 16바이트 솔트(Salt)와 10만 회 키 스트레칭을 적용한 단방향 암호화.
* 비밀번호는 HTML/JS 코드에 일절 포함되지 않고 로컬 파일(`auth_config.json`)에 암호화 보관.
* 비밀번호 파일이 없으면 **초기 비밀번호 생성 마법사** 자동 실행.
* 로그인 전에는 화면 블러 처리 및 모든 데이터 API 원천 차단 (`401 Unauthorized`).

---

## 🛠️ 3. 기술 스택

| 구분 | 기술 / 라이브러리 | 용도 |
| :--- | :--- | :--- |
| **Backend** | **Python 3.10+**, **FastAPI**, **Uvicorn** | 비동기 RESTful 웹 API 서버 |
| **Scraper** | **httpx**, **BeautifulSoup4** | 고속 비동기 BOOTH 메타데이터 페처 |
| **Database** | **SQLite 3** | 로컬 관계형 DB 및 인덱싱, 캐싱 |
| **Translation**| **deep-translator** (Google / MyMemory) | 일본어 ➔ 한국어 스마트 번역 엔진 |
| **Security** | `hashlib` (PBKDF2), `secrets` | 솔트 기반 비밀번호 암호화 및 세션 관리 |
| **Frontend** | **Vue 3 (CDN)**, **Tailwind CSS (CDN)** | 반응형 SPA 다크 모드 웹 인터페이스 |

---

## 📋 4. 시스템 요구사항

* **운영체제**: Windows 10/11, macOS, Linux
* **Python**: **Python 3.10 이상** (필수)
* **Git**: 저장소 복제용
* **인터넷 연결**: BOOTH 썸네일 이미지 로드 및 신규 메타데이터 페치 시 필요

---

## 🚀 5. 설치 및 실행 방법

### 1) 저장소 복제 (Clone)
```bash
git clone https://github.com/your-username/vrcatalogue-web.git
cd vrcatalogue-web
```

### 2) 필수 라이브러리 설치
```bash
py -3.10 -m pip install fastapi uvicorn httpx beautifulsoup4 requests deep-translator huggingface_hub
```

### 3) 베이스 오픈 데이터셋(SQLite) 다운로드
대용량 데이터(임베딩 3.3GB)를 제외한 핵심 메타데이터 DB(`vrcatalogue.sqlite`, 약 140MB)만 Hugging Face에서 다운로드합니다:
```bash
py -3.10 load_db.py
```
*(성공 시 `./data/vrcatalogue.sqlite` 경로에 DB가 준비됩니다.)*

### 4) 서버 실행

#### Windows (원클릭 실행)
프로젝트 루트의 **`start_server.bat`** 파일을 더블 클릭합니다.
*(서버 기동과 함께 브라우저가 자동으로 열립니다.)*

#### 수동 CLI 실행
```bash
py -3.10 -m uvicorn server:app --host 0.0.0.0 --port 8000 --reload
```

### 5) 접속 및 초기 설정
1. 브라우저에서 **`http://127.0.0.1:8000/`** 로 접속합니다.
2. 최초 접속 시 뜨는 **`🔐 초기 비밀번호 생성`** 모달에 원하는 비밀번호(4자리 이상)를 입력합니다.
3. 로컬에 `auth_config.json` 암호화 파일이 자동 생성되며 카탈로그가 즉시 열립니다.
*(같은 Wi-Fi 공유기 내의 스마트폰/태블릿에서도 `http://컴퓨터IP:8000/` 으로 접속 가능합니다.)*

---

## 📂 6. 프로젝트 디렉터리 구조

```text
E:\vrcatalogue\
├── data\
│   └── vrcatalogue.sqlite    # 원본 오픈 데이터셋 (Git 제외)
├── auth_config.json          # 솔트 및 암호화된 비밀번호 보관 파일 (Git 제외)
├── server.py                 # FastAPI 백엔드, 크롤러, 번역 및 인증 라우터
├── index.html                # Vue 3 + Tailwind CSS 통합 프론트엔드 UI
├── load_db.py                # Hugging Face 허브 SQLite 다운로더 스크립트
├── debug_crawler.py          # 신규 에셋 수집기 진단 및 디버거 스크립트
├── start_server.bat          # 윈도우 원클릭 서버 실행 배치 파일
├── .gitignore                # 100MB 이상 대용량 파일 및 보안 설정 제외 목록
└── README.md                 # 프로젝트 문서
```

---

## 📜 7. 라이선스 및 데이터 출처

* **원본 데이터셋**: [vrcatalogue/vrcatalogue-open-data](https://huggingface.co/datasets/vrcatalogue/vrcatalogue-open-data)
* **데이터 라이선스**: [Creative Commons Attribution 4.0 International (CC-BY-4.0)](https://creativecommons.org/licenses/by/4.0/)
* **크레딧**: 본 프로젝트는 VRChat 에셋 생태계에 지대한 공헌을 하고 서비스를 종료한 **VRCatalogue**의 오픈 데이터를 바탕으로 제작되었습니다.