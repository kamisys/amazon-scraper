import os
import time
import requests
from notion_client import Client
from datetime import datetime

NOTION_TOKEN   = os.environ.get("NOTION_TOKEN")
NYT_API_KEY    = os.environ.get("NYT_API_KEY")
PARENT_PAGE_ID = "32c5baf5994c8060b93ad219d197840e"

notion = Client(auth=NOTION_TOKEN)
NYT_REVIEWS_URL = "https://api.nytimes.com/svc/books/v3/reviews.json"

# ✅ 필터링 키워드 — 제목/요약에 이 중 하나라도 포함되면 수집
KEYWORDS = [
    # 한국 음식
    "korean cooking", "korean food", "korean cuisine", "korean recipe",
    "korean kitchen", "korean bbq", "kimchi", "bibimbap", "bulgogi",
    "korean noodle", "korean soup", "korean street food", "korean snack",
    "korean dessert", "korean diet", "korean meal",
    # 한국 식품/재료
    "doenjang", "gochujang", "ganjang", "doenjang", "makgeolli",
    "japchae", "tteok", "jeon", "banchan", "hansik",
    # 한국 문화
    "korean culture", "korean history", "korean tradition", "korean lifestyle",
    "korean beauty", "k-food", "k-culture", "hallyu", "korean wave",
    "temple food", "korean temple", "korean monk",
    # 일반 한국 관련
    "korea", "korean",
]


def is_korean_related(book):
    """제목 또는 요약에 한국 관련 키워드가 포함됐는지 확인"""
    text = (
        book.get("book_title", "") + " " +
        book.get("book_author", "") + " " +
        book.get("summary", "")
    ).lower()  # 소문자로 통일해서 비교

    for kw in KEYWORDS:
        if kw in text:
            return True
    return False


def fetch_books():
    """NYT 리뷰 API로 한국 관련 책 검색"""
    print("NYT Books API 검색 중...")
    if not NYT_API_KEY:
        print("NYT_API_KEY 없음")
        return []

    all_books = []

    # 검색 쿼리 목록
    queries = [
        "korean cooking",
        "korean food",
        "korean culture",
        "korea",
    ]

    for query in queries:
        response = requests.get(
            NYT_REVIEWS_URL,
            params={"api-key": NYT_API_KEY, "query": query},
            timeout=30
        )
        print(f"  [{query}] 응답: {response.status_code}")

        if response.status_code == 200:
            results = response.json().get("results", [])
            print(f"  [{query}] {len(results)}건 발견")
            all_books.extend(results)
        elif response.status_code == 401:
            print("API 키 오류")
            return []
        else:
            print(f"  에러: {response.text[:100]}")

        time.sleep(1)  # API 연속 호출 방지

    return all_books


def parse_book(book):
    return {
        "title":       book.get("book_title", "제목 없음"),
        "author":      book.get("book_author", "저자 불명"),
        "summary":     book.get("summary", "설명 없음"),
        "reviewer":    book.get("byline", ""),
        "review_date": book.get("publication_dt", ""),
        "review_url":  book.get("url", ""),
        "amazon_url":  book.get("amazon_product_url", ""),
    }


def run():
    print("NYT 한국 음식/문화 도서 수집 시작...")

    raw_books = fetch_books()
    if not raw_books:
        print("수집 데이터 없음")
        return

    # ✅ 중복 제거 + 키워드 필터링
    seen, books = set(), []
    filtered_out = 0
    for book in raw_books:
        title = book.get("book_title", "")
        if not title or title in seen:
            continue
        seen.add(title)

        if is_korean_related(book):
            books.append(parse_book(book))
        else:
            filtered_out += 1

    print(f"필터링 결과: {len(books)}권 선택 / {filtered_out}권 제외")

    if not books:
        print("한국 관련 도서가 없습니다.")
        return

    # 리뷰 날짜 최신순 정렬
    books.sort(key=lambda x: x["review_date"], reverse=True)

    # 노션 페이지 생성
    page_title = f"NYT Korean Books {datetime.now().strftime('%Y-%m-%d')}"
    print(f"노션 페이지 생성: {page_title}")

    children = []

    # 페이지 헤더
    children.append({
        "object": "block", "type": "heading_1",
        "heading_1": {"rich_text": [{"type": "text", "text": {
            "content": f"NYT 한국 음식/문화 도서 ({datetime.now().strftime('%Y-%m-%d')})"
        }}]}
    })
    children.append({
        "object": "block", "type": "paragraph",
        "paragraph": {"rich_text": [{"type": "text", "text": {
            "content": f"총 {len(books)}권 | 출처: New York Times Books Review"
        }}]}
    })
    children.append({"object": "block", "type": "divider", "divider": {}})

    # 책마다 섹션
    for i, book in enumerate(books, 1):
        # 제목
        children.append({
            "object": "block", "type": "heading_2",
            "heading_2": {"rich_text": [{"type": "text", "text": {
                "content": f"{i}. {book['title']}"
            }}]}
        })

        # 기본 정보
        info_lines = [
            f"저자: {book['author']}",
            f"리뷰 날짜: {book['review_date']}" if book['review_date'] else None,
            f"NYT 리뷰어: {book['reviewer']}" if book['reviewer'] else None,
            f"요약: {book['summary']}",
        ]
        for line in info_lines:
            if line:
                children.append({
                    "object": "block", "type": "bulleted_list_item",
                    "bulleted_list_item": {"rich_text": [{"type": "text", "text": {
                        "content": line
                    }}]}
                })

        # NYT 리뷰 링크
        if book["review_url"]:
            children.append({
                "object": "block", "type": "paragraph",
                "paragraph": {"rich_text": [{"type": "text", "text": {
                    "content": "NYT 리뷰 원문 보기",
                    "link": {"url": book["review_url"]}
                }}]}
            })

        # 아마존 링크
        if book["amazon_url"]:
            children.append({
                "object": "block", "type": "paragraph",
                "paragraph": {"rich_text": [{"type": "text", "text": {
                    "content": "아마존에서 구매",
                    "link": {"url": book["amazon_url"]}
                }}]}
            })

        # 구분선
        children.append({"object": "block", "type": "divider", "divider": {}})

    # 노션에 페이지 생성 (100개씩 나눠서 전송)
    new_page = notion.pages.create(
        parent={"type": "page_id", "page_id": PARENT_PAGE_ID},
        properties={
            "title": {"title": [{"text": {"content": page_title}}]}
        },
        children=children[:100]
    )
    page_id = new_page["id"]
    print(f"페이지 생성 완료!")

    # 100개 초과분 추가
    if len(children) > 100:
        for i in range(100, len(children), 100):
            time.sleep(1)
            notion.blocks.children.append(
                block_id=page_id,
                children=children[i:i+100]
            )
            print(f"  추가 블록 {min(i+100, len(children))}/{len(children)} 완료")

    print(f"\n완료! {len(books)}권 입력됨 → {page_title}")


if __name__ == "__main__":
    run()
