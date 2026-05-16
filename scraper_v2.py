#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
국가유산청 자연유산위원회 회의록 스크래퍼 (개선 버전)
- 강화된 오류 처리
- 재시도 로직
- 상세한 디버깅 정보
"""

import os
import time
import csv
import re
import json
from pathlib import Path
from urllib.parse import urljoin, urlparse
from typing import List, Dict, Tuple, Optional

import requests
from bs4 import BeautifulSoup
import pdfplumber
import pandas as pd


class CommitteeMeetingScraperV2:
    """국가유산청 자연유산위원회 회의록 스크래퍼 (개선 버전)"""
    
    BASE_URL = "https://www.khs.go.kr/cop/bbs/selectBoardList.do"
    BOARD_ID = "BBSMSTR_1301"
    MN_PARAM = "NS_03_15_04"
    
    KEYWORDS = ["천제연", "중문관광단지", "여미지", "색달동"]
    OUTPUT_DIR = "./회의록"
    RESULTS_FILE = "results.csv"
    DEBUG_FILE = "debug.log"
    
    REQUEST_TIMEOUT = 15
    REQUEST_DELAY = 1.5
    MAX_RETRIES = 3
    
    def __init__(self, verbose: bool = True, debug: bool = True):
        """
        Args:
            verbose: 상세 로깅 출력 여부
            debug: 디버그 정보 저장 여부
        """
        self.verbose = verbose
        self.debug = debug
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        })
        
        # 출력 디렉토리 생성
        Path(self.OUTPUT_DIR).mkdir(exist_ok=True)
        
        self.results = []
        self.downloaded_pdfs = set()
        self.debug_log = []
        self.statistics = {
            'total_pages': 0,
            'total_items': 0,
            'total_pdfs': 0,
            'matched_results': 0,
            'errors': 0
        }
    
    def log(self, msg: str, level: str = "INFO"):
        """로깅"""
        timestamp = time.strftime('%H:%M:%S')
        log_msg = f"[{timestamp}] [{level}] {msg}"
        
        if self.verbose:
            print(log_msg)
        
        if self.debug:
            self.debug_log.append(log_msg)
    
    def fetch_page(self, page_index: int = 1, retry: int = 0) -> Optional[BeautifulSoup]:
        """
        게시판 페이지 fetch (재시도 로직 포함)
        
        Args:
            page_index: 페이지 번호
            retry: 재시도 횟수
            
        Returns:
            BeautifulSoup 객체 또는 None
        """
        params = {
            'bbsId': self.BOARD_ID,
            'mn': self.MN_PARAM,
            'pageIndex': page_index
        }
        
        try:
            self.log(f"페이지 {page_index} 로드 중... (시도: {retry + 1}/{self.MAX_RETRIES})")
            resp = self.session.get(self.BASE_URL, params=params, timeout=self.REQUEST_TIMEOUT)
            resp.encoding = 'utf-8'
            resp.raise_for_status()
            
            # 응답 상태 확인
            if resp.status_code != 200:
                raise requests.RequestException(f"HTTP {resp.status_code}")
            
            time.sleep(self.REQUEST_DELAY)
            self.statistics['total_pages'] += 1
            return BeautifulSoup(resp.text, 'html.parser')
        
        except requests.RequestException as e:
            self.log(f"❌ 페이지 {page_index} 로드 실패: {str(e)}", level="ERROR")
            self.statistics['errors'] += 1
            
            if retry < self.MAX_RETRIES - 1:
                self.log(f"⏳ {2 ** retry}초 후 재시도...")
                time.sleep(2 ** retry)
                return self.fetch_page(page_index, retry + 1)
            
            return None
    
    def extract_board_items(self, soup: BeautifulSoup) -> List[Dict]:
        """
        게시판 리스트에서 항목 추출
        
        Returns:
            {'title': str, 'url': str, 'meeting_no': str, 'date': str} 리스트
        """
        items = []
        
        try:
            # 다양한 테이블 선택자 시도
            table = soup.find('table', class_=re.compile(r'(board|list|table)', re.I))
            if not table:
                # 클래스 없는 테이블 찾기
                tables = soup.find_all('table')
                if tables:
                    # 가장 큰 테이블 선택 (게시판 테이블일 가능성이 높음)
                    table = max(tables, key=lambda t: len(t.find_all('tr')))
            
            if not table:
                self.log("❌ 게시판 테이블을 찾을 수 없습니다", level="WARNING")
                self._save_debug_html(soup, "table_not_found.html")
                return items
            
            # tbody 또는 table 내의 tr 찾기
            rows = table.find_all('tr')[1:]  # 헤더 행 제외
            
            for row_idx, row in enumerate(rows):
                try:
                    cells = row.find_all('td')
                    if len(cells) < 3:
                        continue
                    
                    # 첫 번째 열: 회의 차수
                    meeting_no = cells[0].get_text(strip=True)
                    
                    # 두 번째 열: 회의 일자
                    date = cells[1].get_text(strip=True)
                    
                    # 세 번째 열: 제목 (링크 포함)
                    title_cell = cells[2]
                    link = title_cell.find('a')
                    
                    if not link:
                        continue
                    
                    title = link.get_text(strip=True)
                    url = link.get('href', '')
                    
                    # 상대 URL을 절대 URL로 변환
                    if url and not url.startswith('http'):
                        url = urljoin('https://www.khs.go.kr', url)
                    
                    items.append({
                        'meeting_no': meeting_no,
                        'date': date,
                        'title': title,
                        'url': url
                    })
                    
                except Exception as e:
                    self.log(f"⚠️ 행 {row_idx} 파싱 오류: {str(e)}", level="WARNING")
                    continue
            
            self.log(f"✓ {len(items)}개 항목 추출됨")
            self.statistics['total_items'] += len(items)
            
        except Exception as e:
            self.log(f"❌ 게시판 항목 추출 실패: {str(e)}", level="ERROR")
            self.statistics['errors'] += 1
        
        return items
    
    def has_next_page(self, soup: BeautifulSoup) -> bool:
        """다음 페이지 존재 여부 확인"""
        try:
            # 1. 다음 버튼 찾기
            next_button = soup.find('a', class_=re.compile(r'(next|btn-next|nextPage)', re.I))
            if next_button and next_button.get('href'):
                self.log("다음 페이지 발견 (next 버튼)")
                return True
            
            # 2. 페이지 번호 링크 확인
            pagination = soup.find('div', class_=re.compile(r'pagination|paging', re.I))
            if pagination:
                links = pagination.find_all('a')
                if links:
                    self.log("다음 페이지 발견 (페이지 링크)")
                    return True
            
            return False
        
        except Exception as e:
            self.log(f"⚠️ 다음 페이지 확인 오류: {str(e)}", level="WARNING")
            return False
    
    def fetch_detail_page(self, url: str, retry: int = 0) -> Optional[BeautifulSoup]:
        """상세 페이지 fetch"""
        try:
            self.log(f"상세 페이지 로드: {url[:60]}... (시도: {retry + 1}/{self.MAX_RETRIES})")
            resp = self.session.get(url, timeout=self.REQUEST_TIMEOUT)
            resp.encoding = 'utf-8'
            resp.raise_for_status()
            
            time.sleep(self.REQUEST_DELAY)
            return BeautifulSoup(resp.text, 'html.parser')
        
        except requests.RequestException as e:
            self.log(f"❌ 상세 페이지 로드 실패: {str(e)}", level="ERROR")
            
            if retry < self.MAX_RETRIES - 1:
                time.sleep(2 ** retry)
                return self.fetch_detail_page(url, retry + 1)
            
            return None
    
    def extract_pdfs_from_detail(self, soup: BeautifulSoup) -> List[Tuple[str, str]]:
        """
        상세 페이지에서 PDF 다운로드 링크 추출
        
        Returns:
            [(pdf_url, pdf_filename), ...] 리스트
        """
        pdfs = []
        
        try:
            # PDF 링크 찾기
            links = soup.find_all('a', href=re.compile(r'\.pdf|download|attachment', re.I))
            
            for link in links:
                href = link.get('href', '')
                text = link.get_text(strip=True)
                
                if not href:
                    continue
                
                # 파일명 결정
                filename = text or urlparse(href).path.split('/')[-1]
                
                # 상대 URL을 절대 URL로 변환
                if href and not href.startswith('http'):
                    href = urljoin('https://www.khs.go.kr', href)
                
                pdfs.append((href, filename))
            
            self.log(f"✓ {len(pdfs)}개 PDF 링크 추출됨")
            
        except Exception as e:
            self.log(f"⚠️ PDF 링크 추출 오류: {str(e)}", level="WARNING")
        
        return pdfs
    
    def download_pdfs(self, pdfs: List[Tuple[str, str]]) -> List[str]:
        """
        PDF 파일 다운로드
        
        Args:
            pdfs: [(url, filename), ...] 리스트
            
        Returns:
            다운로드된 파일 경로 리스트
        """
        downloaded = []
        
        for pdf_url, filename in pdfs:
            try:
                # 파일명 정제
                filename = self._sanitize_filename(filename)
                filepath = Path(self.OUTPUT_DIR) / filename
                
                # 이미 다운로드됨
                if filepath.exists():
                    self.log(f"  ⊘ 이미 존재: {filename}")
                    downloaded.append(str(filepath))
                    continue
                
                self.log(f"  ⬇️  {filename} 다운로드 중...")
                resp = self.session.get(pdf_url, timeout=self.REQUEST_TIMEOUT)
                resp.raise_for_status()
                
                # 파일 크기 확인
                file_size = len(resp.content)
                if file_size < 1000:  # 1KB 미만이면 유효하지 않은 파일
                    self.log(f"  ⚠️ 파일 크기 이상: {filename} ({file_size} bytes)", level="WARNING")
                    continue
                
                with open(filepath, 'wb') as f:
                    f.write(resp.content)
                
                downloaded.append(str(filepath))
                self.downloaded_pdfs.add(filename)
                self.statistics['total_pdfs'] += 1
                self.log(f"  ✓ {filename} 다운로드 완료 ({file_size} bytes)")
                time.sleep(self.REQUEST_DELAY)
                
            except Exception as e:
                self.log(f"  ❌ {filename} 다운로드 실패: {str(e)}", level="ERROR")
                self.statistics['errors'] += 1
                continue
        
        return downloaded
    
    def extract_pdf_text(self, pdf_path: str) -> Dict[int, str]:
        """
        PDF에서 텍스트 추출
        
        Args:
            pdf_path: PDF 파일 경로
            
        Returns:
            {page_number: text, ...} 딕셔너리
        """
        text_by_page = {}
        
        try:
            with pdfplumber.open(pdf_path) as pdf:
                for page_num, page in enumerate(pdf.pages, start=1):
                    try:
                        text = page.extract_text() or ""
                        text_by_page[page_num] = text
                    except Exception as e:
                        self.log(f"  ⚠️ 페이지 {page_num} 추출 오류: {str(e)}", level="WARNING")
                        continue
            
            self.log(f"  ✓ {len(text_by_page)}페이지 텍스트 추출됨")
        
        except Exception as e:
            self.log(f"  ❌ PDF 추출 실패: {str(e)}", level="ERROR")
            self.statistics['errors'] += 1
        
        return text_by_page
    
    def search_keywords_in_text(self, text: str, page_num: int) -> List[Dict]:
        """
        텍스트에서 키워드 검색
        
        Returns:
            [{'keyword': str, 'page': int, 'excerpt': str}, ...] 리스트
        """
        matches = []
        
        for keyword in self.KEYWORDS:
            if keyword in text:
                # 발췌 텍스트 추출 (앞뒤 각 50자)
                idx = text.find(keyword)
                start = max(0, idx - 50)
                end = min(len(text), idx + len(keyword) + 50)
                excerpt = text[start:end].replace('\n', ' ').strip()
                
                matches.append({
                    'keyword': keyword,
                    'page': page_num,
                    'excerpt': excerpt
                })
        
        return matches
    
    def process_meeting(self, item: Dict) -> List[Dict]:
        """
        개별 회의 처리
        
        Returns:
            결과 리스트
        """
        meeting_results = []
        
        if not item.get('url'):
            self.log("⚠️ URL 없음, 스킵", level="WARNING")
            return meeting_results
        
        try:
            # 상세 페이지 접근
            detail_soup = self.fetch_detail_page(item['url'])
            if not detail_soup:
                return meeting_results
            
            # PDF 링크 추출 및 다운로드
            pdfs = self.extract_pdfs_from_detail(detail_soup)
            if not pdfs:
                self.log(f"⚠️ PDF 없음: {item['title']}", level="WARNING")
                return meeting_results
            
            downloaded_files = self.download_pdfs(pdfs)
            
            # 각 PDF 분석
            for pdf_path in downloaded_files:
                self.log(f"분석 중: {Path(pdf_path).name}")
                text_by_page = self.extract_pdf_text(pdf_path)
                
                # 각 페이지에서 키워드 검색
                for page_num, text in text_by_page.items():
                    matches = self.search_keywords_in_text(text, page_num)
                    
                    for match in matches:
                        result = {
                            'meeting_no': item['meeting_no'],
                            'date': item['date'],
                            'title': item['title'],
                            'keyword': match['keyword'],
                            'pdf_filename': Path(pdf_path).name,
                            'page_num': match['page'],
                            'excerpt': match['excerpt']
                        }
                        meeting_results.append(result)
                        self.statistics['matched_results'] += 1
        
        except Exception as e:
            self.log(f"❌ 회의 처리 오류: {str(e)}", level="ERROR")
            self.statistics['errors'] += 1
        
        return meeting_results
    
    def save_results(self):
        """결과를 CSV로 저장"""
        if not self.results:
            self.log("저장할 결과가 없습니다", level="WARNING")
            return
        
        try:
            df = pd.DataFrame(self.results)
            
            # 컬럼 순서
            columns = [
                'meeting_no', 'date', 'title', 'keyword',
                'pdf_filename', 'page_num', 'excerpt'
            ]
            df = df[columns]
            
            # 한글 컬럼명
            df.columns = [
                '회의차수', '회의일자', '안건명', '매칭키워드',
                'PDF파일명', '페이지번호', '관련내용발췌'
            ]
            
            df.to_csv(self.RESULTS_FILE, index=False, encoding='utf-8-sig')
            self.log(f"✅ 결과 저장됨: {self.RESULTS_FILE} ({len(df)}개 행)")
        
        except Exception as e:
            self.log(f"❌ 결과 저장 실패: {str(e)}", level="ERROR")
    
    def save_debug_log(self):
        """디버그 로그 저장"""
        if not self.debug_log:
            return
        
        try:
            with open(self.DEBUG_FILE, 'w', encoding='utf-8') as f:
                f.write('\n'.join(self.debug_log))
            self.log(f"✓ 디버그 로그 저장됨: {self.DEBUG_FILE}")
        
        except Exception as e:
            self.log(f"⚠️ 디버그 로그 저장 실패: {str(e)}", level="WARNING")
    
    def save_statistics(self):
        """통계 저장"""
        try:
            stats_file = "statistics.json"
            with open(stats_file, 'w', encoding='utf-8') as f:
                json.dump(self.statistics, f, ensure_ascii=False, indent=2)
            self.log(f"✓ 통계 저장됨: {stats_file}")
        
        except Exception as e:
            self.log(f"⚠️ 통계 저장 실패: {str(e)}", level="WARNING")
    
    def _save_debug_html(self, soup: BeautifulSoup, filename: str):
        """디버그용 HTML 저장"""
        try:
            with open(filename, 'w', encoding='utf-8') as f:
                f.write(str(soup.prettify()))
        except:
            pass
    
    @staticmethod
    def _sanitize_filename(filename: str) -> str:
        """파일명 정제"""
        invalid_chars = r'[<>:"/\\|?*]'
        filename = re.sub(invalid_chars, '_', filename)
        if not filename.lower().endswith('.pdf'):
            filename = filename.replace('.pdf', '') + '.pdf'
        return filename[:255]
    
    def scrape(self):
        """메인 스크래핑 실행"""
        self.log("=" * 70)
        self.log("국가유산청 자연유산위원회 회의록 스크래퍼 시작 (v2)")
        self.log("=" * 70)
        self.log(f"검색 키워드: {', '.join(self.KEYWORDS)}")
        self.log(f"출력 디렉토리: {self.OUTPUT_DIR}")
        self.log("=" * 70)
        
        page_index = 1
        
        while True:
            self.log(f"\n--- 페이지 {page_index} ---")
            
            # 페이지 로드
            soup = self.fetch_page(page_index)
            if not soup:
                self.log("페이지 로드 실패, 중단", level="ERROR")
                break
            
            # 항목 추출
            items = self.extract_board_items(soup)
            if not items:
                self.log("항목 없음, 종료")
                break
            
            # 각 항목 처리
            for i, item in enumerate(items, start=1):
                item_num = (page_index - 1) * len(items) + i
                self.log(f"\n[{item_num}] {item['date']} | {item['title'][:50]}...")
                
                # 회의 처리
                meeting_results = self.process_meeting(item)
                self.results.extend(meeting_results)
                
                if meeting_results:
                    self.log(f"✓ {len(meeting_results)}개 매칭 결과 추가됨")
            
            # 다음 페이지 확인
            if not self.has_next_page(soup):
                self.log("\n마지막 페이지 도달, 종료")
                break
            
            page_index += 1
            self.log(f"\n⏳ 다음 페이지 로드 전 대기 중...")
            time.sleep(2)
        
        # 결과 저장
        self.log("\n" + "=" * 70)
        self.log("스크래핑 완료")
        self.log("=" * 70)
        self.log(f"📊 통계:")
        self.log(f"  - 처리된 페이지: {self.statistics['total_pages']}")
        self.log(f"  - 처리된 항목: {self.statistics['total_items']}")
        self.log(f"  - 다운로드된 PDF: {self.statistics['total_pdfs']}")
        self.log(f"  - 매칭된 결과: {self.statistics['matched_results']}")
        self.log(f"  - 오류 발생: {self.statistics['errors']}")
        self.log("=" * 70)
        
        self.save_results()
        self.save_debug_log()
        self.save_statistics()


def main():
    """메인 함수"""
    scraper = CommitteeMeetingScraperV2(verbose=True, debug=True)
    scraper.scrape()


if __name__ == '__main__':
    main()
