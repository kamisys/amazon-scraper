import os
import time
import requests
from notion_client import Client
from datetime import datetime

NOTION_TOKEN  = os.environ.get("NOTION_TOKEN")
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY", "")
PARENT_PAGE_ID = "32c5baf5994c8060b93ad219d197840e"

notion = Client(auth=NOTION_TOKEN)
GOOGLE_BOOKS_URL = "https://www.googleapis.com/books/v1/volumes"


def fetch_books():
    # ✅ 디버깅: API 키가 실제로 전달됐는지 확인
    if GOOGLE_API_KEY:
        print(f"API 키 확인: {GOOGLE_API_KEY[:8]}... (앞 8자리만 표시)")
    else:
        print("❌ API 키 없음 - GOOGLE_API_KEY 환경변수가 비어있습니다")
        return []

    params = {
        "q":            "korean cooking",
        "maxResults":   20,
        "orderBy":      "relevance",
        "langRestrict": "en",
        "printType":    "books",
        "key":          GOOGLE_API_KEY,   # API 키 항상 포함
    }

    for attempt in range(3):
        response = requests.get(GOOGLE_BOOKS_URL, params=params)
        print(f"응답 코드: {response.status_code}")

        if response.status_code == 200:
            items = response.json().get("items", [])
            print(f"수집된 책 수: {len(items)}권")
            return items

        elif response.status_code == 429:
            # ✅ 디버깅: 429 응답 내용 출력
            print(f"429 응답 내용: {response.text[:300]}")
            wait = 15 * (attempt + 1)
            print(f"  {wait}초 후 재시도... ({attempt+1}/3)")
            time.sleep(wait)

        else:
            # ✅ 디버깅: 기타 에러 내용 출력
            print(f"에러 응답 내용: {response.text[:300]}")
            return []

    return []


def parse_book(item):
    info  = item.get("volumeInfo", {})
    sale  = item.get("saleInfo", {})

    img_url = info.get("imageLinks", {}).get("thumbnail", "").replace("http://", "https://")
    price   = sale.get("listPrice", {}).get("amount", None)

    description = info.get("description", "설명 없음")
    if len(description) > 300:
        description = description[:300] + "..."

    return {
        "title":          info.get("title", "제목 없음"),
        "author":         ", ".join(info.get("authors", ["저자 불명"])),
        "rating":         info.get("averageRating", 0),
        "summary":        description,
        "img_url":        img_url,
        "target":         ", ".join(info.get("categories", ["요리 관심자"])),
        "price_strategy": f"${price}" if price else "가격 정보 없음",
        "publisher":      info.get("publisher", "출판사 불명"),
        "published_date": info.get("publishedDate", "날짜 불명"),
    }


def run():
    print("한국 음식 도서 데이터 수집 시작...")
    raw_books = fetch_books()

    if not raw_books:
        print("수집된 데이터가 없습니다. 위 디버깅 메시지를 확인하세요.")
        return

    # 중복 제거 + 파싱
    seen, books = set(), []
    for item in raw_books:
        title = item.get("volumeInfo", {}).get("title", "")
        if title and title not in seen:
            seen.add(title)
            books.append(parse_book(item))

    books.sort(key=lambda x: x["rating"], reverse=True)
    print(f"총 {len(books)}권 정리 완료")

    # 노션 DB 생성
    db_title = f"Korean Food Books-{datetime.now().strftime('%Y%m%d')}"
    print(f"노션 DB 생성 중: {db_title}")

    new_db = notion.databases.create(
        parent={"type": "page_id", "page_id": PARENT_PAGE_ID},
        title=[{"type": "text", "text": {"content": db_title}}],
        properties={
            "제목":       {"title": {}},
            "저자":       {"rich_text": {}},
            "평점":       {"number": {}},
            "요약":       {"rich_text": {}},
            "표지이미지": {"files": {}},
            "타겟/가격":  {"rich_text": {}},
            "출판사":     {"rich_text": {}},
            "출판연도":   {"rich_text": {}},
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
                "제목":       {"title":     [{"text": {"content": book["title"]}}]},
                "저자":       {"rich_text": [{"text": {"content": book["author"]}}]},
                "평점":       {"number":    book["rating"]},
                "요약":       {"rich_text": [{"text": {"content": book["summary"]}}]},
                "표지이미지": {"files":     files_value},
                "타겟/가격":  {"rich_text": [{"text": {"content": f"타겟: {book['target']}\n가격: {book['price_strategy']}"}}]},
                "출판사":     {"rich_text": [{"text": {"content": book["publisher"]}}]},
                "출판연도":   {"rich_text": [{"text": {"content": book["published_date"]}}]},
            }
        )
        if (i + 1) % 10 == 0:
            print(f"  {i+1}건 입력 완료...")

    print(f"\n완료: {db_title} — 총 {len(books)}권!")


if __name__ == "__main__":
    run()
