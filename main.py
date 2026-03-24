import os
import time
import requests
from notion_client import Client
from datetime import datetime

NOTION_TOKEN   = os.environ.get("NOTION_TOKEN")
NYT_API_KEY    = os.environ.get("NYT_API_KEY")
PARENT_PAGE_ID = "32c5baf5994c8060b93ad219d197840e"

notion = Client(auth=NOTION_TOKEN)

# ✅ 베스트셀러 히스토리 API (title= 파라미터로 검색 가능 - 실제 작동 확인된 엔드포인트)
NYT_HISTORY_URL = "https://api.nytimes.com/svc/books/v3/lists/best-sellers/history.json"


def fetch_books():
    """NYT 베스트셀러 히스토리 API로 한국 관련 책 검색"""
    print("NYT 베스트셀러 히스토리 검색 중...")
    if not NYT_API_KEY:
        print("NYT_API_KEY 없음")
        return []

    all_books = []

    # title= 파라미터로 한국 관련 키워드 검색
    search_keywords = [
        "korean",
        "kimchi",
        "korea",
        "korean cooking",
        "korean food",
    ]

    for keyword in search_keywords:
        response = requests.get(
            NYT_HISTORY_URL,
            params={"api-key": NYT_API_KEY, "title": keyword},
            timeout=30
        )
        print(f"  [{keyword}] 응답: {response.status_code}")

        if response.status_code == 200:
            results = response.json().get("results", [])
            print(f"  [{keyword}] {len(results)}권 발견")
            all_books.extend(results)
        elif response.status_code == 401:
            print("❌ API 키 오류")
            return []
        else:
            print(f"  에러: {response.text[:150]}")

        time.sleep(1)  # API 호출 간격

    return all_books


def run():
    print("NYT 한국 도서 데이터 수집 시작...")

    raw_books = fetch_books()
    if not raw_books:
        print("수집 데이터 없음")
        return

    # 중복 제거 (title 기준)
    seen, books = set(), []
    for book in raw_books:
        # 히스토리 API는 book_details 리스트 안에 제목이 있음
        details = book.get("book_details", [{}])
        title = details[0].get("title", "") if details else ""
        if title and title not in seen:
            seen.add(title)
            books.append(book)

    print(f"중복 제거 후 총 {len(books)}권")
    if not books:
        print("데이터 없음")
        return

    # 노션 페이지 생성
    page_title = f"NYT Korean Books {datetime.now().strftime('%Y-%m-%d')}"
    print(f"노션 페이지 생성: {page_title}")

    children = []

    # 헤더
    children.append({
        "object": "block", "type": "heading_1",
        "heading_1": {"rich_text": [{"type": "text", "text": {
            "content": f"NYT 한국 음식/문화 도서 ({datetime.now().strftime('%Y-%m-%d')})"
        }}]}
    })
    children.append({
        "object": "block", "type": "paragraph",
        "paragraph": {"rich_text": [{"type": "text", "text": {
            "content": f"총 {len(books)}권 | 출처: NYT Best Sellers History"
        }}]}
    })
    children.append({"object": "block", "type": "divider", "divider": {}})

    for i, book in enumerate(books, 1):
        details = book.get("book_details", [{}])
        d = details[0] if details else {}

        title     = d.get("title", "제목 없음")
        author    = d.get("author", "저자 불명")
        publisher = d.get("publisher", "출판사 불명")
        desc      = d.get("description", "설명 없음")
        price     = d.get("price", "")

        # 베스트셀러 이력 (몇 주, 어떤 리스트)
        ranks = book.get("ranks_history", [])
        best_rank  = min((r.get("rank", 99) for r in ranks), default="-")
        total_weeks = len(set(r.get("published_date", "") for r in ranks))
        lists_on   = list(set(r.get("list_name", "") for r in ranks))[:3]
        list_names = ", ".join(lists_on) if lists_on else "정보 없음"

        # 제목 블록
        children.append({
            "object": "block", "type": "heading_2",
            "heading_2": {"rich_text": [{"type": "text", "text": {
                "content": f"{i}. {title}"
            }}]}
        })

        # 정보 블록
        info_lines = [
            f"저자: {author}",
            f"출판사: {publisher}",
            f"최고 순위: {best_rank}위",
            f"베스트셀러 기간: 약 {total_weeks}주",
            f"등재 리스트: {list_names}",
            f"가격: ${price}" if price else None,
            f"설명: {desc}" if desc and desc != "설명 없음" else None,
        ]
        for line in info_lines:
            if line:
                children.append({
                    "object": "block", "type": "bulleted_list_item",
                    "bulleted_list_item": {"rich_text": [{"type": "text", "text": {
                        "content": line
                    }}]}
                })

        # ISBN 기반 아마존 링크 생성
        isbns = book.get("isbns", [])
        if isbns:
            isbn13 = isbns[0].get("isbn13", "")
            if isbn13:
                amz_url = f"https://www.amazon.com/dp/{isbn13}"
                children.append({
                    "object": "block", "type": "paragraph",
                    "paragraph": {"rich_text": [{"type": "text", "text": {
                        "content": "아마존에서 보기",
                        "link": {"url": amz_url}
                    }}]}
                })

        children.append({"object": "block", "type": "divider", "divider": {}})

    # 노션 페이지 저장 (100개씩 나눠서)
    new_page = notion.pages.create(
        parent={"type": "page_id", "page_id": PARENT_PAGE_ID},
        properties={"title": {"title": [{"text": {"content": page_title}}]}},
        children=children[:100]
    )
    page_id = new_page["id"]

    if len(children) > 100:
        for i in range(100, len(children), 100):
            time.sleep(1)
            notion.blocks.children.append(
                block_id=page_id,
                children=children[i:i+100]
            )
            print(f"  블록 추가 {min(i+100, len(children))}/{len(children)}")

    print(f"\n완료! {len(books)}권 → Notion 저장됨!")


if __name__ == "__main__":
    run()
