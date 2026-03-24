import os
import requests
from firecrawl import FirecrawlApp
from notion_client import Client
from datetime import datetime

# GitHub Secrets에서 가져오기
FIRECRAWL_KEY = os.environ.get("FIRECRAWL_API_KEY")
NOTION_TOKEN = os.environ.get("NOTION_TOKEN")
PARENT_PAGE_ID = "32c5baf5994c8060b93ad219d197840e" # KDP 페이지 ID

notion = Client(auth=NOTION_TOKEN)
app = FirecrawlApp(api_key=FIRECRAWL_KEY)

def run():
    print("아마존 데이터 수집 시작...")
    # 1. 아마존 데이터 수집 (최신 scrape_url API 방식 적용)
    # 'schema' 대신 'formats'와 'extract' 옵션을 사용하는 최신 규격으로 수정함
    scrape_result = app.scrape(
        "https://www.amazon.com/Best-Sellers-Books-Korean-Cooking-Food-Wine/zgbs/books/624448",
        params={
            "formats": ["extract"],
            "extract": {
                "prompt": "Extract books with rating 4.5+. Translate summaries into direct Korean (직설스타일). Identify target audience and pricing strategy.",
                "schema": {
                    "type": "object",
                    "properties": {
                        "items": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "title": {"type": "string"},
                                    "author": {"type": "string"},
                                    "rating": {"type": "number"},
                                    "rank": {"type": "integer"},
                                    "summary": {"type": "string"},
                                    "img_url": {"type": "string"},
                                    "target": {"type": "string"},
                                    "price_strategy": {"type": "string"}
                                }
                            }
                        }
                    }
                }
            }
        }
    )

    # 데이터 추출 (구조 확인)
    data = scrape_result.get('extract', {}).get('items', [])
    if not data:
        print("수집된 데이터가 없습니다. 평점 4.5 이상인 도서가 현재 페이지에 있는지 확인이 필요합니다.")
        return

    # 2. 노션 DB 생성
    print("노션 데이터베이스 생성 중...")
    db_title = f"Korean food 베스트셀러-{datetime.now().strftime('%Y%m%d')}"
    new_db = notion.databases.create(
        parent={"type": "page_id", "page_id": PARENT_PAGE_ID},
        title=[{"type": "text", "text": {"content": db_title}}],
        properties={
            "제목": {"title": {}},
            "순위": {"number": {}},
            "요약(한글)": {"rich_text": {}},
            "표지이미지": {"files": {}},
            "타겟/가격전략": {"rich_text": {}}
        }
    )
    db_id = new_db["id"]

    # 3. 데이터 입력
    print(f"데이터 입력 중 ({len(data)}건)...")
    for item in data:
        notion.pages.create(
            parent={"database_id": db_id},
            properties={
                "제목": {"title": [{"text": {"content": item.get('title', 'N/A')}}]},
                "순위": {"number": item.get('rank', 0)},
                "요약(한글)": {"rich_text": [{"text": {"content": item.get('summary', '요약 없음')}}]},
                "표지이미지": {"files": [{"name": "Cover", "external": {"url": item.get('img_url', 'https://via.placeholder.com/150')}}]},
                "타겟/가격전략": {"rich_text": [{"text": {"content": f"타겟: {item.get('target', 'N/A')}\n전략: {item.get('price_strategy', 'N/A')}"}}]}
            }
        )
    print(f"완료: {db_title} 생성 및 데이터 입력 완료!")

if __name__ == "__main__":
    run()