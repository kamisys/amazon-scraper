import os
import requests
from notion_client import Client
from datetime import datetime

NOTION_TOKEN   = os.environ.get("NOTION_TOKEN")
NYT_API_KEY    = os.environ.get("NYT_API_KEY")
PARENT_PAGE_ID = "32c5baf5994c8060b93ad219d197840e"

notion = Client(auth=NOTION_TOKEN)

# NYT Books API - 베스트셀러 목록 엔드포인트
NYT_LISTS_URL  = "https://api.nytimes.com/svc/books/v3/lists/current/{list_name}.json"
# NYT Books API - 책 검색 엔드포인트  
NYT_SEARCH_URL = "https://api.nytimes.com/svc/books/v3/reviews.json"


def fetch_nyt_books():
    """NYT Books API로 요리 관련 베스트셀러 수집"""
    print("NYT Books API 검색 중...")
    print(f"API 키 확인: {NYT_API_KEY[:8] if NYT_API_KEY else '없음'}...")

    if not NYT_API_KEY:
        print("❌ NYT_API_KEY 환경변수가 없습니다. GitHub Secrets 확인하세요.")
        return []

    all_books = []

    # NYT 베스트셀러 카테고리 목록
    # food-and-diet = 음식/다이어트, advice-how-to-and-miscellaneous = 실용서
    list_names = [
        "food-and-diet",              # 음식 & 다이어트 베스트셀러
        "advice-how-to-and-miscellaneous",  # 실용 베스트셀러
    ]

    for list_name in list_names:
        url = NYT_LISTS_URL.format(list_name=list_name)
        params = {"api-key": NYT_API_KEY}

        response = requests.get(url, params=params, timeout=30)
        print(f"  [{list_name}] 응답 코드: {response.status_code}")

        if response.status_code == 200:
            data    = response.json()
            results = data.get("results", {}).get("books", [])
            print(f"  [{list_name}] 수집: {len(results)}권")
            all_books.extend(results)

        elif response.status_code == 401:
            print("❌ API 키가 잘못됐거나 Books API가 활성화되지 않았습니다.")
            return []

        else:
            print(f"  [{list_name}] 에러: {response.text[:150]}")

    return all_books


def parse_book(book):
    """NYT Books API 응답에서 필요한 필드 추출"""

    # 표지 이미지 URL
    img_url = book.get("book_image", "")

    # 순위
    rank = book.get("rank", 0)

    # 주간 판매 순위 변동 (+면 상승, -면 하락)
    rank_last = book.get("rank_last_week", 0)
    if rank_last == 0:
        trend = "신규 진입"
    elif rank < rank_last:
        trend = f"▲{rank_last - rank} 상승"
    elif rank > rank_last:
        trend = f"▼{rank - rank_last} 하락"
    else:
        trend = "유지"

    # 연속 베스트셀러 주수
    weeks = book.get("weeks_on_list", 0)

    return {
        "title":       book.get("title", "제목 없음"),
        "author":      book.get("author", "저자 불명"),
        "rank":        rank,
        "publisher":   book.get("publisher", "출판사 불명"),
        "description": book.get("description", "설명 없음"),
        "img_url":     img_url,
        "trend":       trend,
        "weeks":       f"{weeks}주 연속 베스트셀러",
        "amazon_url":  book.get("amazon_product_url", ""),
    }


def run():
    print("NYT 베스트셀러 도서 데이터 수집 시작...")

    raw_books = fetch_nyt_books()

    if not raw_books:
        print("수집된 데이터가 없습니다.")
        return

    # 중복 제거 + 파싱
    seen, books = set(), []
    for book in raw_books:
        title = book.get("title", "")
        if title and title not in seen:
            seen.add(title)
            books.append(parse_book(book))

    # 순위 순 정렬
    books.sort(key=lambda x: x["rank"])
    print(f"총 {len(books)}권 수집 완료")

    # 노션 DB 생성
    db_title = f"NYT 베스트셀러-{datetime.now().strftime('%Y%m%d')}"
    print(f"노션 DB 생성: {db_title}")

    new_db = notion.databases.create(
        parent={"type": "page_id", "page_id": PARENT_PAGE_ID},
        title=[{"type": "text", "text": {"content": db_title}}],
        properties={
            "제목":         {"title": {}},
            "저자":         {"rich_text": {}},
            "순위":         {"number": {}},
            "출판사":       {"rich_text": {}},
            "설명":         {"rich_text": {}},
            "표지이미지":   {"files": {}},
            "순위변동":     {"rich_text": {}},
            "베스트셀러기간": {"rich_text": {}},
            "아마존링크":   {"url": {}},
        }
    )
    db_id = new_db["id"]

    print(f"노션 입력 중 ({len(books)}건)...")
    for i, book in enumerate(books):
        files_value = (
            [{"name": "Cover", "external": {"url": book["img_url"]}}]
            if book["img_url"] else []
        )
        notion.pages.create(
            parent={"database_id": db_id},
            properties={
                "제목":         {"title":     [{"text": {"content": book["title"]}}]},
                "저자":         {"rich_text": [{"text": {"content": book["author"]}}]},
                "순위":         {"number":    book["rank"]},
                "출판사":       {"rich_text": [{"text": {"content": book["publisher"]}}]},
                "설명":         {"rich_text": [{"text": {"content": book["description"]}}]},
                "표지이미지":   {"files":     files_value},
                "순위변동":     {"rich_text": [{"text": {"content": book["trend"]}}]},
                "베스트셀러기간": {"rich_text": [{"text": {"content": book["weeks"]}}]},
                "아마존링크":   {"url": book["amazon_url"] if book["amazon_url"] else None},
            }
        )
        if (i + 1) % 10 == 0:
            print(f"  {i+1}건 입력 완료...")

    print(f"\n완료: {db_title} — 총 {len(books)}권 입력됨!")


if __name__ == "__main__":
    run()
