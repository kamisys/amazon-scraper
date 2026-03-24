import os
import time
import requests
from notion_client import Client
from datetime import datetime

NOTION_TOKEN   = os.environ.get("NOTION_TOKEN")
NYT_API_KEY    = os.environ.get("NYT_API_KEY")
PARENT_PAGE_ID = "32c5baf5994c8060b93ad219d197840e"

notion = Client(auth=NOTION_TOKEN)

# ✅ 이미 200 응답 확인된 엔드포인트만 사용
NYT_LIST_URL = "https://api.nytimes.com/svc/books/v3/lists/current/{list_name}.json"

# 한국 음식/식품/문화 필터 키워드
KEYWORDS = [
    "korean", "korea", "kimchi", "bibimbap", "bulgogi",
    "gochujang", "tteok", "banchan", "hansik", "k-food",
    "hallyu", "temple food", "asian food", "asian cooking",
    "japanese", "chinese", "thai", "vietnamese", "asian",
    "food", "cooking", "recipe", "cuisine", "kitchen",
    "eat", "chef", "ingredient", "flavor", "diet",
]

# KDP 전략상 관심 있는 NYT 베스트셀러 리스트 (200 응답 확인된 것들)
LIST_NAMES = [
    "hardcover-nonfiction",
    "advice-how-to-and-miscellaneous",
    "paperback-nonfiction",
    "combined-print-and-e-book-nonfiction",
]


def is_food_or_culture(book):
    """제목 또는 설명에 음식/문화 관련 키워드 포함 여부"""
    text = (
        book.get("title", "") + " " + book.get("description", "")
    ).lower()
    return any(kw in text for kw in KEYWORDS)


def fetch_books():
    print("NYT 베스트셀러 수집 중...")
    all_books = []

    for list_name in LIST_NAMES:
        response = requests.get(
            NYT_LIST_URL.format(list_name=list_name),
            params={"api-key": NYT_API_KEY},
            timeout=30
        )
        print(f"  [{list_name}] 응답: {response.status_code}")

        if response.status_code == 200:
            results = response.json().get("results", {}).get("books", [])
            print(f"  [{list_name}] {len(results)}권")
            all_books.extend(results)
        else:
            print(f"  [{list_name}] 스킵")

        time.sleep(0.5)

    return all_books


def run():
    print("KDP 도서 데이터 수집 시작...")

    raw_books = fetch_books()
    if not raw_books:
        print("수집 데이터 없음")
        return

    print(f"전체 수집: {len(raw_books)}권")

    # 중복 제거
    seen, unique = set(), []
    for book in raw_books:
        title = book.get("title", "")
        if title and title not in seen:
            seen.add(title)
            unique.append(book)

    # 음식/문화 키워드 필터링
    filtered = [b for b in unique if is_food_or_culture(b)]
    print(f"음식/문화 관련 필터링: {len(filtered)}권 선택")

    # 필터링 결과 없으면 전체 사용
    if not filtered:
        print("필터 결과 없음 → 전체 사용")
        filtered = unique

    # 노션 페이지 생성
    page_title = f"NYT Food & Culture Books {datetime.now().strftime('%Y-%m-%d')}"
    print(f"노션 저장 중: {page_title}")

    children = []

    children.append({
        "object": "block", "type": "heading_1",
        "heading_1": {"rich_text": [{"type": "text", "text": {
            "content": f"NYT 음식/문화 도서 ({datetime.now().strftime('%Y-%m-%d')})"
        }}]}
    })
    children.append({
        "object": "block", "type": "paragraph",
        "paragraph": {"rich_text": [{"type": "text", "text": {
            "content": f"총 {len(filtered)}권 | NYT 베스트셀러 기반 | 음식/문화/한국 키워드 필터"
        }}]}
    })
    children.append({"object": "block", "type": "divider", "divider": {}})

    for i, book in enumerate(filtered, 1):
        rank      = book.get("rank", "-")
        rank_last = book.get("rank_last_week", 0)
        weeks     = book.get("weeks_on_list", 0)

        if rank_last == 0:             trend = "신규"
        elif book["rank"] < rank_last: trend = f"▲{rank_last - book['rank']}"
        elif book["rank"] > rank_last: trend = f"▼{book['rank'] - rank_last}"
        else:                          trend = "유지"

        children.append({
            "object": "block", "type": "heading_2",
            "heading_2": {"rich_text": [{"type": "text", "text": {
                "content": f"#{rank} {book.get('title', '제목 없음')}"
            }}]}
        })

        for line in [
            f"저자: {book.get('author', '저자 불명')}",
            f"출판사: {book.get('publisher', '')}",
            f"순위변동: {trend} | {weeks}주 연속",
            f"설명: {book.get('description', '')}",
        ]:
            if line.split(': ', 1)[-1].strip():
                children.append({
                    "object": "block", "type": "bulleted_list_item",
                    "bulleted_list_item": {"rich_text": [{"type": "text", "text": {"content": line}}]}
                })

        amz = book.get("amazon_product_url", "")
        if amz:
            children.append({
                "object": "block", "type": "paragraph",
                "paragraph": {"rich_text": [{"type": "text", "text": {
                    "content": "아마존 링크", "link": {"url": amz}
                }}]}
            })

        children.append({"object": "block", "type": "divider", "divider": {}})

    # 노션 페이지 저장
    new_page = notion.pages.create(
        parent={"type": "page_id", "page_id": PARENT_PAGE_ID},
        properties={"title": {"title": [{"text": {"content": page_title}}]}},
        children=children[:100]
    )
    page_id = new_page["id"]

    for i in range(100, len(children), 100):
        time.sleep(1)
        notion.blocks.children.append(
            block_id=page_id,
            children=children[i:i+100]
        )

    print(f"\n완료! {len(filtered)}권 저장됨!")


if __name__ == "__main__":
    run()
