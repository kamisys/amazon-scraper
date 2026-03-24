import os
import requests
from firecrawl import Firecrawl          # ✅ 수정1: FirecrawlApp → Firecrawl (신버전 클래스명)
from notion_client import Client
from datetime import datetime

# GitHub Secrets에서 환경변수 가져오기
FIRECRAWL_KEY = os.environ.get("FIRECRAWL_API_KEY")
NOTION_TOKEN = os.environ.get("NOTION_TOKEN")
PARENT_PAGE_ID = "32c5baf5994c8060b93ad219d197840e"  # KDP 페이지 ID

# 노션 클라이언트 생성
notion = Client(auth=NOTION_TOKEN)

# ✅ 수정2: FirecrawlApp → Firecrawl (신버전 클래스명으로 객체 생성)
app = Firecrawl(api_key=FIRECRAWL_KEY)


def run():
    print("아마존 데이터 수집 시작...")

    # ✅ 수정3: scrape_url() → scrape() (신버전 메서드명으로 변경)
    # params={} 딕셔너리 방식 → 직접 인자 방식으로 변경
    scrape_result = app.scrape(
        "https://www.amazon.com/Best-Sellers-Books-Korean-Cooking-Food-Wine/zgbs/books/624448",
        formats=["extract"],           # 어떤 형식으로 데이터를 받을지 지정
        extract={
            "prompt": "Extract books with rating 4.5+. Translate summaries into direct Korean (직설스타일). Identify target audience and pricing strategy.",
            "schema": {
                "type": "object",
                "properties": {
                    "items": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "title":          {"type": "string"},
                                "author":         {"type": "string"},
                                "rating":         {"type": "number"},
                                "rank":           {"type": "integer"},
                                "summary":        {"type": "string"},
                                "img_url":        {"type": "string"},
                                "target":         {"type": "string"},
                                "price_strategy": {"type": "string"}
                            }
                        }
                    }
                }
            }
        }
    )

    # ✅ 수정4: 데이터 꺼내는 방식 변경
    # 구버전: scrape_result.get('extract', {}).get('items', [])  → 딕셔너리['키'] 방식
    # 신버전: scrape_result.extract.get('items', [])             → 객체.속성 방식
    raw = scrape_result.extract if scrape_result.extract else {}
    data = raw.get("items", [])

    # 데이터가 없으면 경고 출력 후 종료
    if not data:
        print("수집된 데이터가 없습니다. 평점 4.5 이상인 도서가 현재 페이지에 있는지 확인이 필요합니다.")
        return

    # 2. 노션 데이터베이스 생성
    print("노션 데이터베이스 생성 중...")
    db_title = f"Korean food 베스트셀러-{datetime.now().strftime('%Y%m%d')}"

    new_db = notion.databases.create(
        parent={"type": "page_id", "page_id": PARENT_PAGE_ID},
        title=[{"type": "text", "text": {"content": db_title}}],
        properties={
            "제목":          {"title": {}},
            "순위":          {"number": {}},
            "요약(한글)":    {"rich_text": {}},
            "표지이미지":    {"files": {}},
            "타겟/가격전략": {"rich_text": {}}
        }
    )
    db_id = new_db["id"]  # 새로 만든 DB의 고유 ID 저장

    # 3. 수집한 데이터를 노션에 한 건씩 입력
    print(f"데이터 입력 중 ({len(data)}건)...")
    for item in data:
        notion.pages.create(
            parent={"database_id": db_id},
            properties={
                "제목":          {"title":     [{"text": {"content": item.get("title", "N/A")}}]},
                "순위":          {"number":    item.get("rank", 0)},
                "요약(한글)":    {"rich_text": [{"text": {"content": item.get("summary", "요약 없음")}}]},
                "표지이미지":    {"files":     [{"name": "Cover", "external": {"url": item.get("img_url", "https://via.placeholder.com/150")}}]},
                "타겟/가격전략": {"rich_text": [{"text": {"content": f"타겟: {item.get('target', 'N/A')}\n전략: {item.get('price_strategy', 'N/A')}"}}]}
            }
        )

    print(f"완료: {db_title} 생성 및 데이터 입력 완료!")


if __name__ == "__main__":
    run()