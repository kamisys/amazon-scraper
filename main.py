import os
import time
import requests
from notion_client import Client
from datetime import datetime

NOTION_TOKEN = os.environ.get("NOTION_TOKEN")
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY", "")  # 있으면 사용, 없어도 됨
PARENT_PAGE_ID = "32c5baf5994c8060b93ad219d197840e"

notion = Client(auth=NOTION_TOKEN)
GOOGLE_BOOKS_URL = "https://www.googleapis.com/books/v1/volumes"


def fetch_books_with_retry(query, max_results=40, retries=3):
    """429 에러 나면 잠깐 기다렸다가 재시도"""
    params = {
        "q": query,
        "maxResults": max_results,   # 한 번에 최대 40개 (API 한도)
        "orderBy": "relevance",
        "langRestrict": "en",
        "printType": "books",
    }
    # API 키가 있으면 추가 (하루 1000건 → 10000건으로 한도 증가)
    if GOOGLE_API_KEY:
        params["key"] = GOOGLE_API_KEY

    for attempt in range(retries):
        response = requests.get(GOOGLE_BOOKS_URL, params=params)

        if response.status_code == 200:
            return response.json().get("items", [])

        elif response.status_code == 429:
            # 429: 요청이 너무 많음 → 10초 기다렸다가 재시도
            wait = 10 * (attempt + 1)  # 10초, 20초, 30초 순으로 대기
            print(f"  429 차단됨. {wait}초 후 재시도... ({attempt+1}/{retries})")
            time.sleep(wait)

        else:
            print(f"  검색 실패: {response.status_code}")
            return []

    print(f"  {retries}번 모두 실패. 검색 포기.")
    return []


def parse_book(item):
    """Google Books 응답에서 필요한 필드 추출"""
    info = item.get("volumeInfo", {})
    sale = item.get("saleInfo", {})

    rating = info.get("averageRating", 0)
    images = info.get("imageLinks", {})
    img_url = images.get("thumbnail", "").replace("http://", "https://")  # https로 통일

    price = sale.get("listPrice", {}).get("amount", None)
    price_str = f"${price}" if price else "가격 정보 없음"

    categories = info.get("categories", [])
    target = ", ".join(categories) if categories else "요리 관심자"

    description = info.get("description", "설명 없음")
    if len(description) > 300:
        description = description[:300] + "..."

    return {
        "title":          info.get("title", "제목 없음"),
        "author":         ", ".join(info.get("authors", ["저자 불명"])),
        "rating":         rating,
        "summary":        description,
        "img_url":        img_url,
        "target":         target,
        "price_strategy": price_str,
        "publisher":      info.get("publisher", "출판사 불명"),
        "published_date": info.get("publishedDate", "날짜 불명"),
    }


def run():
    print("한국 음식 도서 데이터 수집 시작...")

    # ✅ 핵심 수정: 검색 3번 → 1번으로 줄임 (429 방지)
    # "korean cooking food" 하나로 합쳐서 한 번만 요청
    print("Google Books API 검색 중...")
    raw_books = fetch_books_with_retry("korean cooking food recipe", max_results=40)

    if not raw_books:
        print("수집된 데이터가 없습니다.")
        print("→ GitHub Secrets에 GOOGLE_API_KEY 추가를 권장합니다.")
        return

    # 중복 제거 + 파싱
    seen = set()
    books = []
    for item in raw_books:
        title = item.get("volumeInfo", {}).get("title", "")
        if title and title not in seen:
            seen.add(title)
            books.append(parse_book(item))

    # 평점 높은 순 정렬
    books.sort(key=lambda x: x["rating"], reverse=True)
    print(f"총 {len(books)}권 수집 완료")

    # 노션 DB 생성
    print("노션 데이터베이스 생성 중...")
    db_title = f"Korean Food Books-{datetime.now().strftime('%Y%m%d')}"

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

    # 노션에 입력
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

    print(f"\n완료: {db_title} — 총 {len(books)}권 입력됨!")


if __name__ == "__main__":
    run()
