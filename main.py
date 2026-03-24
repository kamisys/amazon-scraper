import os
import time
import requests
from notion_client import Client
from datetime import datetime

NOTION_TOKEN   = os.environ.get("NOTION_TOKEN")
NYT_API_KEY    = os.environ.get("NYT_API_KEY")
PARENT_PAGE_ID = "32c5baf5994c8060b93ad219d197840e"

notion = Client(auth=NOTION_TOKEN)
NYT_LISTS_URL = "https://api.nytimes.com/svc/books/v3/lists/current/{list_name}.json"


def fetch_nyt_books():
    print("NYT Books API 검색 중...")
    if not NYT_API_KEY:
        print("NYT_API_KEY 없음")
        return []

    all_books = []
    for list_name in ["hardcover-nonfiction", "advice-how-to-and-miscellaneous"]:
        response = requests.get(
            NYT_LISTS_URL.format(list_name=list_name),
            params={"api-key": NYT_API_KEY},
            timeout=30
        )
        print(f"  [{list_name}] 응답: {response.status_code}")
        if response.status_code == 200:
            results = response.json().get("results", {}).get("books", [])
            print(f"  [{list_name}] {len(results)}권")
            all_books.extend(results)
    return all_books


def parse_book(book):
    rank      = book.get("rank", 0)
    rank_last = book.get("rank_last_week", 0)
    if rank_last == 0:       trend = "신규 진입"
    elif rank < rank_last:   trend = f"▲{rank_last - rank} 상승"
    elif rank > rank_last:   trend = f"▼{rank - rank_last} 하락"
    else:                    trend = "유지"

    return {
        "title":       book.get("title", "제목 없음"),
        "author":      book.get("author", "저자 불명"),
        "rank":        rank,
        "publisher":   book.get("publisher", "출판사 불명"),
        "description": book.get("description", "설명 없음"),
        "img_url":     book.get("book_image", ""),
        "trend":       trend,
        "weeks":       book.get("weeks_on_list", 0),
        "amazon_url":  book.get("amazon_product_url", ""),
    }


def run():
    print("NYT 베스트셀러 수집 시작...")

    raw_books = fetch_nyt_books()
    if not raw_books:
        print("수집 데이터 없음")
        return

    # 중복 제거 + 파싱
    seen, books = set(), []
    for book in raw_books:
        title = book.get("title", "")
        if title and title not in seen:
            seen.add(title)
            books.append(parse_book(book))
    books.sort(key=lambda x: x["rank"])
    print(f"총 {len(books)}권")

    # ✅ 방식 변경: DB 속성 대신 → 그냥 페이지 하나 만들고 본문에 책 목록 작성
    # Notion DB 속성 생성 문제를 완전히 우회하는 방법
    page_title = f"NYT Bestsellers {datetime.now().strftime('%Y-%m-%d')}"
    print(f"노션 페이지 생성: {page_title}")

    # 책 목록을 본문 블록으로 만들기
    children = []

    # 날짜 헤더
    children.append({
        "object": "block",
        "type": "heading_1",
        "heading_1": {
            "rich_text": [{"type": "text", "text": {"content": page_title}}]
        }
    })

    # 책마다 섹션 추가
    for book in books:
        # 책 제목 (heading_2)
        children.append({
            "object": "block",
            "type": "heading_2",
            "heading_2": {
                "rich_text": [{"type": "text", "text": {
                    "content": f"#{book['rank']} {book['title']}"
                }}]
            }
        })

        # 책 정보 (bullet points)
        info_lines = [
            f"저자: {book['author']}",
            f"출판사: {book['publisher']}",
            f"순위변동: {book['trend']}",
            f"베스트셀러 기간: {book['weeks']}주 연속",
            f"설명: {book['description']}",
        ]
        for line in info_lines:
            children.append({
                "object": "block",
                "type": "bulleted_list_item",
                "bulleted_list_item": {
                    "rich_text": [{"type": "text", "text": {"content": line}}]
                }
            })

        # 아마존 링크
        if book["amazon_url"]:
            children.append({
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [{
                        "type": "text",
                        "text": {
                            "content": "아마존 링크",
                            "link": {"url": book["amazon_url"]}
                        }
                    }]
                }
            })

        # 구분선
        children.append({
            "object": "block",
            "type": "divider",
            "divider": {}
        })

    # ✅ Notion 페이지 생성 (블록은 100개씩 나눠서 전송 - API 한도)
    print("노션 페이지 생성 중...")
    new_page = notion.pages.create(
        parent={"type": "page_id", "page_id": PARENT_PAGE_ID},
        properties={
            "title": {"title": [{"text": {"content": page_title}}]}
        },
        children=children[:100]   # 첫 100개 블록
    )
    page_id = new_page["id"]
    print(f"페이지 생성 완료: {page_id}")

    # 100개 초과분 추가 입력
    if len(children) > 100:
        print("추가 블록 입력 중...")
        for i in range(100, len(children), 100):
            time.sleep(1)
            notion.blocks.children.append(
                block_id=page_id,
                children=children[i:i+100]
            )
            print(f"  {min(i+100, len(children))}/{len(children)} 블록 완료")

    print(f"\n완료! {len(books)}권 입력됨 → Notion 페이지: {page_title}")


if __name__ == "__main__":
    run()
