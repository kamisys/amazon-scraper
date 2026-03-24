import os
import requests                      # 인터넷 요청용 (기본 내장)
from notion_client import Client     # 노션에 데이터 넣기용
from datetime import datetime        # 날짜/시간 표시용

# GitHub Secrets에서 환경변수 가져오기
NOTION_TOKEN = os.environ.get("NOTION_TOKEN")
PARENT_PAGE_ID = "32c5baf5994c8060b93ad219d197840e"  # KDP 페이지 ID

# 노션 클라이언트 생성
notion = Client(auth=NOTION_TOKEN)

# Google Books API 주소 (API 키 불필요, 무료)
GOOGLE_BOOKS_URL = "https://www.googleapis.com/books/v1/volumes"


def fetch_korean_food_books():
    """Google Books API로 한국 음식 관련 영어책 검색"""
    print("Google Books API로 데이터 수집 중...")

    all_books = []

    # 검색어 목록 - 여러 키워드로 최대한 많이 수집
    search_queries = [
        "korean cooking",
        "korean food recipe",
        "korean cuisine",
    ]

    for query in search_queries:
        params = {
            "q": query,              # 검색어
            "maxResults": 20,        # 최대 20개 결과
            "orderBy": "relevance",  # 관련도 순 정렬
            "langRestrict": "en",    # 영어 책만
            "printType": "books",    # 책만 (잡지 제외)
        }

        response = requests.get(GOOGLE_BOOKS_URL, params=params)

        # 응답이 실패하면 다음 검색어로 넘어감
        if response.status_code != 200:
            print(f"검색 실패 ({query}): {response.status_code}")
            continue

        items = response.json().get("items", [])
        print(f"  '{query}' 검색 결과: {len(items)}건")
        all_books.extend(items)

    return all_books


def parse_book(item):
    """Google Books API 응답에서 필요한 필드만 꺼내기"""
    info = item.get("volumeInfo", {})    # 책 기본 정보
    sale = item.get("saleInfo", {})      # 판매 정보

    # 평점 (없으면 0)
    rating = info.get("averageRating", 0)

    # 표지 이미지 URL (없으면 빈 문자열)
    images = info.get("imageLinks", {})
    img_url = images.get("thumbnail", "")

    # 가격 정보
    price = sale.get("listPrice", {}).get("amount", None)
    price_str = f"${price}" if price else "가격 정보 없음"

    # 타겟 독자 (카테고리 기반 추정)
    categories = info.get("categories", [])
    target = ", ".join(categories) if categories else "요리 관심자"

    # 책 설명 (없으면 기본 문구)
    description = info.get("description", "설명 없음")
    # 너무 길면 300자로 자르기
    if len(description) > 300:
        description = description[:300] + "..."

    return {
        "title":          info.get("title", "제목 없음"),
        "author":         ", ".join(info.get("authors", ["저자 불명"])),
        "rating":         rating,
        "page_count":     info.get("pageCount", 0),
        "summary":        description,
        "img_url":        img_url,
        "target":         target,
        "price_strategy": price_str,
        "publisher":      info.get("publisher", "출판사 불명"),
        "published_date": info.get("publishedDate", "날짜 불명"),
    }


def run():
    print("한국 음식 도서 데이터 수집 시작...")

    # 1. Google Books API로 책 목록 가져오기
    raw_books = fetch_korean_food_books()

    if not raw_books:
        print("수집된 데이터가 없습니다.")
        return

    # 2. 중복 제거 (제목 기준)
    seen_titles = set()
    books = []
    for item in raw_books:
        title = item.get("volumeInfo", {}).get("title", "")
        if title and title not in seen_titles:
            seen_titles.add(title)
            books.append(parse_book(item))

    # 3. 평점 높은 순으로 정렬 (평점 없는 책은 맨 뒤로)
    books.sort(key=lambda x: x["rating"], reverse=True)

    print(f"중복 제거 후 총 {len(books)}권 수집 완료")

    # 4. 노션 데이터베이스 생성
    print("노션 데이터베이스 생성 중...")
    db_title = f"Korean Food Books-{datetime.now().strftime('%Y%m%d')}"

    new_db = notion.databases.create(
        parent={"type": "page_id", "page_id": PARENT_PAGE_ID},
        title=[{"type": "text", "text": {"content": db_title}}],
        properties={
            "제목":        {"title": {}},       # 책 제목
            "저자":        {"rich_text": {}},   # 저자명
            "평점":        {"number": {}},      # Google 평점
            "요약":        {"rich_text": {}},   # 책 설명
            "표지이미지":  {"files": {}},       # 표지 이미지
            "타겟/가격":   {"rich_text": {}},   # 타겟 독자 + 가격
            "출판사":      {"rich_text": {}},   # 출판사
            "출판연도":    {"rich_text": {}},   # 출판 날짜
        }
    )
    db_id = new_db["id"]
    print(f"DB 생성 완료: {db_title}")

    # 5. 데이터를 노션에 한 건씩 입력
    print(f"노션 입력 중 ({len(books)}건)...")
    for i, book in enumerate(books):
        # 이미지 URL 있을 때만 파일 필드에 넣기
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
                "타겟/가격":  {"rich_text": [{"text": {"content": (
                    f"타겟: {book['target']}\n가격: {book['price_strategy']}"
                )}}]},
                "출판사":     {"rich_text": [{"text": {"content": book["publisher"]}}]},
                "출판연도":   {"rich_text": [{"text": {"content": book["published_date"]}}]},
            }
        )
        # 10건마다 진행상황 출력
        if (i + 1) % 10 == 0:
            print(f"  {i + 1}건 입력 완료...")

    print(f"\n✅ 완료: {db_title} — 총 {len(books)}권 입력됨!")


if __name__ == "__main__":
    run()
