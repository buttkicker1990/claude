# 국가유산청 자연유산위원회 회의록 스크래퍼

국가유산청 자연유산위원회 회의록 게시판에서 특정 키워드가 포함된 안건을 찾고, PDF를 분석하여 결과를 CSV로 저장하는 스크래퍼입니다.

## 🎯 기능

- ✅ 게시판 전체 페이지 순회 및 항목 추출
- ✅ PDF 파일 자동 다운로드
- ✅ pdfplumber를 이용한 PDF 텍스트 추출
- ✅ 4가지 키워드 검색 및 매칭
- ✅ 결과를 UTF-8 CSV로 저장

## 🔍 검색 키워드

- 천제연
- 중문관광단지
- 여미지
- 색달동

## 📋 요구사항

- Python 3.8+
- requests (HTTP 요청)
- beautifulsoup4 (HTML 파싱)
- pdfplumber (PDF 텍스트 추출)
- pandas (CSV 저장)

## 🚀 설치 및 실행

### 1. 의존성 설치

```bash
pip install -r requirements.txt
```

### 2. 스크래퍼 실행

```bash
python scraper.py
```

## 📊 출력 결과

### 디렉토리 구조

```
./
├── scraper.py
├── requirements.txt
├── results.csv          # 검색 결과
└── 회의록/               # 다운로드된 PDF 파일들
    ├── 회의록_001.pdf
    ├── 회의록_002.pdf
    └── ...
```

### results.csv 포맷

| 컬럼 | 설명 |
|------|------|
| 회의차수 | 회의 차수 (예: 1차, 2차) |
| 회의일자 | 회의 개최 날짜 |
| 안건명 | 안건 제목 |
| 매칭키워드 | 검색된 키워드 |
| PDF파일명 | 다운로드된 PDF 파일 이름 |
| 페이지번호 | 키워드가 발견된 PDF 페이지 번호 |
| 관련내용발췌 | 키워드 주변 텍스트 (±50자) |

#### 예시

```csv
회의차수,회의일자,안건명,매칭키워드,PDF파일명,페이지번호,관련내용발췌
1차,2026-05-16,제주자연유산 보존현황,천제연,meeting_001.pdf,3, ... 천제연 주변의 자연환경 보호 방안 ...
```

## ⚙️ 설정 수정

`scraper.py` 파일을 열어서 다음 부분을 수정할 수 있습니다:

```python
class CommitteeMeetingScraper:
    # 게시판 URL (변경 불필요)
    BASE_URL = "https://www.khs.go.kr/cop/bbs/selectBoardList.do"
    BOARD_ID = "BBSMSTR_1301"
    
    # 검색 키워드
    KEYWORDS = ["천제연", "중문관광단지", "여미지", "색달동"]
    
    # 출력 디렉토리
    OUTPUT_DIR = "./회의록"
    
    # 결과 파일명
    RESULTS_FILE = "results.csv"
    
    # 요청 타임아웃 (초)
    REQUEST_TIMEOUT = 10
    
    # 페이지 간 대기 시간 (초)
    REQUEST_DELAY = 1
```

## 🔧 주요 메서드

### `scrape()`
메인 스크래핑 실행 메서드. 게시판 전체 순회 후 결과를 저장합니다.

### `fetch_page(page_index)`
특정 페이지의 게시판 HTML을 로드합니다.

### `extract_board_items(soup)`
게시판 페이지에서 회의 항목들을 추출합니다.

### `process_meeting(item, url)`
개별 회의의 상세 페이지를 처리하고 PDF를 다운로드/분석합니다.

### `extract_pdf_text(pdf_path)`
PDF 파일에서 모든 페이지의 텍스트를 추출합니다.

### `search_keywords_in_text(text, page_num)`
텍스트에서 키워드를 검색하고 매칭된 발췌문을 추출합니다.

### `save_results()`
결과를 CSV 파일로 저장합니다.

## 📝 로그 출력

실행 중 다음과 같은 로그 메시지가 표시됩니다:

```
[15:30:45] ============================================================
[15:30:45] 국가유산청 자연유산위원회 회의록 스크래퍼 시작
[15:30:45] ============================================================
[15:30:45] 페이지 1 로드 중...
[15:30:46] ✓ 10개 항목 추출됨

[15:30:47] [1] 2026-05-16 - 제주자연유산 보존현황...
[15:30:47] 상세 페이지 로드: https://www.khs.go.kr/...
[15:30:48] ✓ 2개 PDF 링크 추출됨
[15:30:48]   ⬇️  회의록_001.pdf 다운로드 중...
[15:30:49] 분석 중: 회의록_001.pdf
[15:30:50]   ✓ 10페이지 텍스트 추출됨
[15:30:50] ✓ 2개 매칭 결과 추가됨

...

[15:35:12] ============================================================
[15:35:12] 총 50개 회의 처리됨
[15:35:12] ✅ 결과 저장됨: results.csv (15개 행)
[15:35:12] ============================================================
```

## 🐛 문제 해결

### HTML 구조가 다른 경우

사이트의 HTML 구조가 변경된 경우, `scraper.py`의 다음 부분을 수정해야 합니다:

#### 1. 테이블 선택자 (`extract_board_items`)
```python
table = soup.find('table', class_='your_board_class')
```

#### 2. PDF 링크 선택자 (`extract_pdfs_from_detail`)
```python
links = soup.find_all('a', href=re.compile(r'your_pattern'))
```

#### 3. 페이지네이션 선택자 (`has_next_page`)
```python
next_button = soup.find('a', class_='your_next_class')
```

### PDF 다운로드 실패

- 파일 권한 확인
- 네트워크 연결 확인
- `REQUEST_TIMEOUT` 값 증가 시도

### 키워드 미발견

- 한글 인코딩 확인
- 공백/줄바꿈으로 인한 키워드 분리 확인
- PDF 보안 설정 확인

## 📄 라이선스

MIT License

## 👤 작성자

Created by Copilot for Korean National Heritage Committee Meeting Records Analysis
