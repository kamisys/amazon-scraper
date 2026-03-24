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
    list_names = [
        "hardcover-nonfiction",
        "advice-how-to-and-miscellaneous",
    ]

    for list_name in list_names:
        url      = NYT_LISTS_URL.format(list_name=list_name)
        response = requests.get(url, params={"api-key": NYT_API_KEY}, timeout=30)
        print(f"  [{list_name}] 응답: {response.status_code}")

        if response.status_code == 200:
            results = response.json().get("results", {}).get("books", [])
            print(f"  [{list_name}] {len(results)}권 수집")
            all_books.extend(results)
        elif response.status_code == 401:
            print("API 키 오류")
            return []
        else:
            print(f"  [{list_name}] 에러: {response.text[:100]}")

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
        "weeks":       f"{book.get('weeks_on_list', 0)}주 연속",
        "amazon_url":  book.get("amazon_product_url", ""),
    }


def create_page(db_id, book):
    """노션 페이지 1건 생성 — 에러시 재시도 1회"""
    files_value = (
        [{"name": "Cover", "external": {"url": book["img_url"]}}]
        if book["img_url"] else []
    )
    amazon_url = book["amazon_url"] if book["amazon_url"] else None

    # ✅ 핵심 수정: 영어 키로 DB 생성 후 한글 표시명은 별도 처리
    # Notion API는 property 이름을 생성 시 정의한 키와 정확히 일치시켜야 함
    props = {
        "title":    {"title":     [{"text": {"content": book["title"]}}]},
        "author":   {"rich_text": [{"text": {"content": book["author"]}}]},
        "rank":     {"number":    book["rank"]},
        "pub":      {"rich_text": [{"text": {"content": book["publisher"]}}]},
        "desc":     {"rich_text": [{"text": {"content": book["description"]}}]},
        "img":      {"files":     files_value},
        "trend":    {"rich_text": [{"text": {"content": book["trend"]}}]},
        "weeks":    {"rich_text": [{"text": {"content": book["weeks"]}}]},
        "amz_url":  {"url":       amazon_url},
    }

    for attempt in range(2):  # 실패하면 1번 재시도
        try:
            notion.pages.create(
                parent={"database_id": db_id},
                properties=props
            )
            return True
        except Exception as e:
            print(f"    입력 실패 (시도 {attempt+1}/2): {str(e)[:80]}")
            time.sleep(2)
    return False


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

    # ✅ 핵심: 영어 키로 DB 생성 (한글 키 대신 영어 키 사용 → 인코딩 문제 없음)
    db_title = f"NYT Bestsellers {datetime.now().strftime('%Y%m%d')}"
    print(f"노션 DB 생성: {db_title}")

    new_db = notion.databases.create(
        parent={"type": "page_id", "page_id": PARENT_PAGE_ID},
        title=[{"type": "text", "text": {"content": db_title}}],
        properties={
            "title":   {"title": {}},           # 제목
            "author":  {"rich_text": {}},        # 저자
            "rank":    {"number": {}},           # 순위
            "pub":     {"rich_text": {}},        # 출판사
            "desc":    {"rich_text": {}},        # 설명
            "img":     {"files": {}},            # 표지
            "trend":   {"rich_text": {}},        # 순위변동
            "weeks":   {"rich_text": {}},        # 베스트셀러 기간
            "amz_url": {"url": {}},              # 아마존 링크
        }
    )
    db_id = new_db["id"]
    print(f"DB 생성 완료: {db_id}")

    # ✅ DB 생성 후 실제로 조회해서 준비됐는지 확인
    print("DB 준비 확인 중...")
    for i in range(5):   # 최대 5번 확인 (10초)
        time.sleep(2)
        try:
            db_check = notion.databases.retrieve(database_id=db_id)
            props = list(db_check.get("properties", {}).keys())
            print(f"  DB 속성 확인: {props}")
            if "title" in props:
                print("  DB 준비 완료!")
                break
        except Exception as e:
            print(f"  DB 조회 실패 ({i+1}/5): {e}")
    
    # 데이터 입력
    print(f"노션 입력 중 ({len(books)}건)...")
    success = 0
    for i, book in enumerate(books):
        ok = create_page(db_id, book)
        if ok:
            success += 1
            print(f"  {i+1}. {book['title']} ✓")

    print(f"\n완료: {success}/{len(books)}권 입력됨!")


if __name__ == "__main__":
    run()
