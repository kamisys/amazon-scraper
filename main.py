import os
import requests
from notion_client import Client
from datetime import datetime

NOTION_TOKEN   = os.environ.get("NOTION_TOKEN")
PARENT_PAGE_ID = "32c5baf5994c8060b93ad219d197840e"

notion = Client(auth=NOTION_TOKEN)

# Open Library API (Internet Archive 운영 - 무료, 키 없음, IP 차단 없음)
SEARCH_URL  = "https://openlibrary.org/search.json"
COVER_URL   = "https://covers.openlibrary.org/b/id/{cover_id}-M.jpg"


def fetch_books():
    """Open Library에서 한국 음식 관련 책 검색"""
    print("Open Library API 검색 중...")

    params = {
        "q":       "korean cooking",   # 검색어
        "limit":   40,                 # 최대 40권
        "lang":    "eng",              # 영어 책
        "fields":  "title,author_name,ratings_average,cover_i,subject,publisher,first_publish_year,description",
    }

    response = requests.get(SEARCH_URL, params=params, timeout=30)
    print(f"응답 코드: {response.status_code}")

    if response.status_code != 200:
        print(f"에러 내용: {response.text[:200]}")
        return []

    docs = response.json().get("docs", [])
    print(f"수집된 책 수: {len(docs)}권")
    return docs


def parse_book(doc):
    """Open Library 응답에서 필요한 필드 추출"""

    # 표지 이미지 URL (cover_i = 표지 ID)
    cover_id = doc.get("cover_i")
    img_url  = COVER_URL.format(cover_id=cover_id) if cover_id else ""

    # 평점 (없으면 0)
    rating = doc.get("ratings_average", 0) or 0
    rating = round(float(rating), 1)

    # 타겟 독자 (subject 태그 기반, 최대 3개)
    subjects = doc.get("subject", [])
    target   = ", ".join(subjects[:3]) if subjects else "요리 관심자"

    # 출판사 (리스트면 첫 번째만)
    publishers = doc.get("publisher", [])
    publisher  = publishers[0] if publishers else "출판사 불명"

    # 저자 (리스트면 첫 번째만)
    authors = doc.get("author_name", [])
    author  = authors[0] if authors else "저자 불명"

    return {
        "title":        doc.get("title", "제목 없음"),
        "author":       author,
        "rating":       rating,
        "img_url":      img_url,
        "target":       target,
        "publisher":    publisher,
        "published_year": str(doc.get("first_publish_year", "연도 불명")),
    }


def run():
    print("한국 음식 도서 데이터 수집 시작...")

    raw_books = fetch_books()

    if not raw_books:
        print("수집된 데이터가 없습니다.")
        return

    # 중복 제거 + 파싱
    seen, books = set(), []
    for doc in raw_books:
        title = doc.get("title", "")
        if title and title not in seen:
            seen.add(title)
            books.append(parse_book(doc))

    # 평점 높은 순 정렬
    books.sort(key=lambda x: x["rating"], reverse=True)
    print(f"중복 제거 후 총 {len(books)}권")

    # 노션 DB 생성
    db_title = f"Korean Food Books-{datetime.now().strftime('%Y%m%d')}"
    print(f"노션 DB 생성: {db_title}")

    new_db = notion.databases.create(
        parent={"type": "page_id", "page_id": PARENT_PAGE_ID},
        title=[{"type": "text", "text": {"content": db_title}}],
        properties={
            "제목":     {"title": {}},
            "저자":     {"rich_text": {}},
            "평점":     {"number": {}},
            "표지이미지": {"files": {}},
            "타겟독자": {"rich_text": {}},
            "출판사":   {"rich_text": {}},
            "출판연도": {"rich_text": {}},
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
                "제목":     {"title":     [{"text": {"content": book["title"]}}]},
                "저자":     {"rich_text": [{"text": {"content": book["author"]}}]},
                "평점":     {"number":    book["rating"]},
                "표지이미지": {"files":   files_value},
                "타겟독자": {"rich_text": [{"text": {"content": book["target"]}}]},
                "출판사":   {"rich_text": [{"text": {"content": book["publisher"]}}]},
                "출판연도": {"rich_text": [{"text": {"content": book["published_year"]}}]},
            }
        )
        if (i + 1) % 10 == 0:
            print(f"  {i+1}건 입력 완료...")

    print(f"\n완료: {db_title} — 총 {len(books)}권 입력됨!")


if __name__ == "__main__":
    run()
