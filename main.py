import os
import time
import requests
from notion_client import Client
from datetime import datetime

NOTION_TOKEN   = os.environ.get("NOTION_TOKEN")
NYT_API_KEY    = os.environ.get("NYT_API_KEY")
PARENT_PAGE_ID = "32c5baf5994c8060b93ad219d197840e"

notion = Client(auth=NOTION_TOKEN)

# NYT 리뷰 API - 파라미터: title= (query= 아님)
NYT_REVIEWS_URL = "https://api.nytimes.com/svc/books/v3/reviews.json"

# 한국 음식/식품/문화 필터링 키워드
KEYWORDS = [
    "korean", "korea", "kimchi", "bibimbap", "bulgogi", "gochujang",
    "doenjang", "tteok", "banchan", "hansik", "k-food", "hallyu",
    "korean wave", "temple food", "korean temple", "korean culture",
    "korean cooking", "korean food", "korean cuisine", "korean recipe",
]


def is_korean_related(book):
    """제목 또는 요약에 한국 관련 키워드 포함 여부 확인"""
    text = (
        book.get("book_title", "") + " " + book.get("summary", "")
    ).lower()
    return any(kw in text for kw in KEYWORDS)


def fetch_books():
    """NYT 리뷰 API로 한국 관련 책 검색 (title= 파라미터 사용)"""
    print("NYT Books API 검색 중...")
    if not NYT_API_KEY:
        print("NYT_API_KEY 없음")
        return []

    all_books = []

    # ✅ 수정: query= → title= 로 변경 (NYT API 올바른 파라미터)
    search_titles = [
        "korean cooking",
        "korean food",
        "korean",
        "kimchi",
        "korea",
    ]

    for title in search_titles:
        response = requests.get(
            NYT_REVIEWS_URL,
            params={"api-key": NYT_API_KEY, "title": title},
            timeout=30
        )
        print(f"  [{title}] 응답: {response.status_code}")

        if response.status_code == 200:
            results = response.json().get("results", [])
            print(f"  [{title}] {len(results)}건 발견")
            all_books.extend(results)
        elif response.status_code == 401:
            print("API 키 오류")
            return []
        else:
            print(f"  에러: {response.text[:100]}")

        time.sleep(1)   # API 연속 호출 방지

    return all_books


def run():
    print("NYT 한국 음식/문화 도서 수집 시작...")

    raw_books = fetch_books()
    if not raw_books:
        print("수집 데이터 없음")
        return

    # 중복 제거
    seen, books = set(), []
    for book in raw_books:
        title = book.get("book_title", "")
        if title and title not in seen:
            seen.add(title)
            books.append(book)

    print(f"중복 제거 후 {len(books)}권")

    # 한국 관련 필터링
    filtered = [b for b in books if is_korean_related(b)]
    print(f"한국 관련 필터링 후 {len(filtered)}권")

    # 필터링 후 너무 적으면 필터 없이 전체 사용
    if len(filtered) == 0:
        print("필터링 결과 없음 → 전체 결과 사용")
        filtered = books

    # 날짜 최신순 정렬
    filtered.sort(key=lambda x: x.get("publication_dt", ""), reverse=True)

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
            "content": f"총 {len(filtered)}권 | 출처: New York Times Books"
        }}]}
    })
    children.append({"object": "block", "type": "divider", "divider": {}})

    # 책마다 섹션
    for i, book in enumerate(filtered, 1):
        children.append({
            "object": "block", "type": "heading_2",
            "heading_2": {"rich_text": [{"type": "text", "text": {
                "content": f"{i}. {book.get('book_title', '제목 없음')}"
            }}]}
        })

        info_lines = [
            f"저자: {book.get('book_author', '저자 불명')}",
            f"리뷰 날짜: {book.get('publication_dt', '')}" if book.get('publication_dt') else None,
            f"NYT 리뷰어: {book.get('byline', '')}" if book.get('byline') else None,
            f"요약: {book.get('summary', '설명 없음')}",
        ]
        for line in info_lines:
            if line:
                children.append({
                    "object": "block", "type": "bulleted_list_item",
                    "bulleted_list_item": {"rich_text": [{"type": "text", "text": {
                        "content": line
                    }}]}
                })

        if book.get("url"):
            children.append({
                "object": "block", "type": "paragraph",
                "paragraph": {"rich_text": [{"type": "text", "text": {
                    "content": "NYT 리뷰 원문",
                    "link": {"url": book["url"]}
                }}]}
            })

        if book.get("amazon_product_url"):
            children.append({
                "object": "block", "type": "paragraph",
                "paragraph": {"rich_text": [{"type": "text", "text": {
                    "content": "아마존 링크",
                    "link": {"url": book["amazon_product_url"]}
                }}]}
            })

        children.append({"object": "block", "type": "divider", "divider": {}})

    # 노션 페이지 생성 (100개씩)
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

    print(f"\n완료! {len(filtered)}권 → Notion 저장됨!")


if __name__ == "__main__":
    run()
