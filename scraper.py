#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
국가유산청 자연유산위원회 회의록 스크래퍼
- 게시판 전체 페이지 순회
- PDF 다운로드
- 텍스트 추출 및 키워드 검색
- 결과를 CSV로 저장
"""

import os
import time
import csv
import re
from pathlib import Path
from urllib.parse import urljoin, urlparse
from typing import List, Dict, Tuple, Optional

import requests
from bs4 import BeautifulSoup
import pdfplumber
import pandas as pd


class CommitteeMeetingScraper:
    """국가유산청 자연유산위원회 회의록 스크래퍼"""
    
    BASE_URL = "https://www.khs.go.kr/cop/bbs/selectBoardList.do"
    BOARD_ID = "BBSMSTR_1301"
    MN_PARAM = "NS_03_15_04"
    
    KEYWORDS = ["천제연", "중문관광단지", "여미지", "색달동"]
    OUTPUT_DIR = "./회의록"
    RESULTS_FILE = "results.csv"
    
    REQUEST_TIMEOUT = 10
    REQUEST_DELAY = 1  # 초 단위, 서버 부하 방지
    
    def __init__(self, verbose: bool = True):
        """
        Args:
            verbose: 상세 로깅 출력 여부
        """
        self.verbose = verbose
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        
        # 출력 디렉토리 생성
        Path(self.OUTPUT_DIR).mkdir(exist_ok=True)
        
        self.results = []
        self.downloaded_pdfs = set()
    
    def log(self, msg: str):
        """로깅"""
        if self.verbose:
            print(f"[{time.strftime('%H:%M:%S')}] {msg}")
    
    def fetch_page(self, page_index: int = 1) -> Optional[BeautifulSoup]:
        """
        게시판 페이지 fetch
        
        Args:
            page_index: 페이지 번호 (1부터 시작)
            
        Returns:
            BeautifulSoup 객체 또는 None
        """
        params = {
            'bbsId': self.BOARD_ID,
            'mn': self.MN_PARAM,
            'pageIndex': page_index
        }
        
        try:
            self.log(f"페이지 {page_index} 로드 중...")
            resp = self.session.get(self.BASE_URL, params=params, timeout=self.REQUEST_TIMEOUT)
            resp.encoding = 'utf-8'
            resp.raise_for_status()
            
            time.sleep(self.REQUEST_DELAY)
            return BeautifulSoup(resp.text, 'html.parser')
        
        except requests.RequestException as e:
            self.log(f"❌ 페이지 {page_index} 로드 실패: {e}")
            return None
    
    def extract_board_items(self, soup: BeautifulSoup) -> List[Dict]:
        """
        게시판 리스트에서 항목 추출
        
        Returns:
            {'title': str, 'url': str, 'meeting_no': str, 'date': str} 리스트
        """
        items = []
        
        # 다양한 테이블 선택자 시도
        table = soup.find('table', class_=re.compile(r'(board|list|table)', re.I))
        if not table:
            table = soup.find('table')
        
        if not table:
            self.log("❌ 게시판 테이블을 찾을 수 없습니다")
            return items
        
        # tbody 또는 table 내의 tr 찾기
        rows = table.find_all('tr')[1:]  # 헤더 행 제외
        
        for row in rows:
            try:
                cells = row.find_all('td')
                if len(cells) < 3:
                    continue
                
                # 첫 번째 열: 회의 차수 (또는 번호)
                meeting_no = cells[0].get_text(strip=True)
                
                # 두 번째 열: 회의 일자
                date = cells[1].get_text(strip=True)
                
                # 세 번째 열: 제목/안건명 (링크 포함)
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
                self.log(f"⚠️ 행 파싱 오류: {e}")
                continue
        
        self.log(f"✓ {len(items)}개 항목 추출됨")
        return items
    
    def has_next_page(self, soup: BeautifulSoup) -> bool:
        """다음 페이지 존재 여부 확인"""
        # 다양한 다음 버튼 선택자 시도
        next_button = soup.find('a', class_=re.compile(r'(next|pagination)', re.I))
        if next_button and next_button.get('href'):
            return True
        
        # 페이지 번호 링크 확인
        pagination = soup.find('div', class_=re.compile(r'pagination', re.I))
        if pagination:
            return bool(pagination.find('a'))
        
        return False
    
    def fetch_detail_page(self, url: str) -> Optional[BeautifulSoup]:
        """상세 페이지 fetch"""
        try:
            self.log(f"상세 페이지 로드: {url[:80]}...")
            resp = self.session.get(url, timeout=self.REQUEST_TIMEOUT)
            resp.encoding = 'utf-8'
            resp.raise_for_status()
            
            time.sleep(self.REQUEST_DELAY)
            return BeautifulSoup(resp.text, 'html.parser')
        
        except requests.RequestException as e:
            self.log(f"❌ 상세 페이지 로드 실패: {e}")
            return None
    
    def extract_pdfs_from_detail(self, soup: BeautifulSoup) -> List[Tuple[str, str]]:
        """
        상세 페이지에서 PDF 다운로드 링크 추출
        
        Returns:
            [(pdf_url, pdf_filename), ...] 리스트
        """
        pdfs = []
        
        # PDF 링크 찾기 (여러 선택자 시도)
        links = soup.find_all('a', href=re.compile(r'\.pdf|download', re.I))
        
        for link in links:
            href = link.get('href', '')
            filename = link.get_text(strip=True) or urlparse(href).path.split('/')[-1]
            
            if href:
                # 상대 URL을 절대 URL로 변환
                if not href.startswith('http'):
                    href = urljoin('https://www.khs.go.kr', href)
                
                pdfs.append((href, filename))
        
        self.log(f"✓ {len(pdfs)}개 PDF 링크 추출됨")
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
                
                with open(filepath, 'wb') as f:
                    f.write(resp.content)
                
                downloaded.append(str(filepath))
                self.downloaded_pdfs.add(filename)
                time.sleep(self.REQUEST_DELAY)
                
            except Exception as e:
                self.log(f"  ❌ {filename} 다운로드 실패: {e}")
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
                    text = page.extract_text() or ""
                    text_by_page[page_num] = text
            
            self.log(f"  ✓ {len(text_by_page)}페이지 텍스트 추출됨")
        
        except Exception as e:
            self.log(f"  ❌ PDF 추출 실패: {e}")
        
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
                excerpt = text[start:end].replace('\n', ' ')
                
                matches.append({
                    'keyword': keyword,
                    'page': page_num,
                    'excerpt': excerpt
                })
        
        return matches
    
    def process_meeting(self, item: Dict, meeting_detail_url: str) -> List[Dict]:
        """
        개별 회의 처리: PDF 다운로드 및 분석
        
        Returns:
            결과 리스트 (키워드 매칭된 항목들)
        """
        meeting_results = []
        
        # 상세 페이지 접근
        detail_soup = self.fetch_detail_page(meeting_detail_url)
        if not detail_soup:
            return meeting_results
        
        # PDF 링크 추출 및 다운로드
        pdfs = self.extract_pdfs_from_detail(detail_soup)
        if not pdfs:
            self.log(f"⚠️ PDF를 찾을 수 없음: {item['title']}")
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
                    meeting_results.append({
                        'meeting_no': item['meeting_no'],
                        'date': item['date'],
                        'title': item['title'],
                        'keyword': match['keyword'],
                        'pdf_filename': Path(pdf_path).name,
                        'page_num': match['page'],
                        'excerpt': match['excerpt']
                    })
        
        return meeting_results
    
    def save_results(self):
        """결과를 CSV로 저장"""
        if not self.results:
            self.log("저장할 결과가 없습니다")
            return
        
        df = pd.DataFrame(self.results)
        
        # 컬럼 순서
        columns = [
            'meeting_no', 'date', 'title', 'keyword',
            'pdf_filename', 'page_num', 'excerpt'
        ]
        df = df[columns]
        
        # 한글 컬럼명으로 변경
        df.columns = [
            '회의차수', '회의일자', '안건명', '매칭키워드',
            'PDF파일명', '페이지번호', '관련내용발췌'
        ]
        
        df.to_csv(self.RESULTS_FILE, index=False, encoding='utf-8-sig')
        self.log(f"✅ 결과 저장됨: {self.RESULTS_FILE} ({len(df)}개 행)")
    
    @staticmethod
    def _sanitize_filename(filename: str) -> str:
        """파일명에서 불허용 문자 제거"""
        invalid_chars = r'[<>:"/\\|?*]'
        filename = re.sub(invalid_chars, '_', filename)
        filename = filename.replace('.pdf', '') + '.pdf'
        return filename[:255]  # 파일명 길이 제한
    
    def scrape(self):
        """메인 스크래핑 실행"""
        self.log("=" * 60)
        self.log("국가유산청 자연유산위원회 회의록 스크래퍼 시작")
        self.log("=" * 60)
        
        page_index = 1
        total_items = 0
        
        while True:
            # 페이지 로드
            soup = self.fetch_page(page_index)
            if not soup:
                break
            
            # 항목 추출
            items = self.extract_board_items(soup)
            if not items:
                self.log("항목이 없습니다")
                break
            
            total_items += len(items)
            
            # 각 항목 처리
            for i, item in enumerate(items, start=1):
                self.log(f"\n[{total_items - len(items) + i}] {item['date']} - {item['title'][:50]}...")
                
                if not item['url']:
                    self.log("⚠️ URL 없음, 스킵")
                    continue
                
                # 회의 상세 정보 처리
                meeting_results = self.process_meeting(item, item['url'])
                self.results.extend(meeting_results)
                
                if meeting_results:
                    self.log(f"✓ {len(meeting_results)}개 매칭 결과 추가됨")
            
            # 다음 페이지 확인
            if not self.has_next_page(soup):
                self.log("\n마지막 페이지입니다")
                break
            
            page_index += 1
        
        # 결과 저장
        self.log("\n" + "=" * 60)
        self.log(f"총 {total_items}개 회의 처리됨")
        self.save_results()
        self.log("=" * 60)


def main():
    """메인 함수"""
    scraper = CommitteeMeetingScraper(verbose=True)
    scraper.scrape()


if __name__ == '__main__':
    main()
