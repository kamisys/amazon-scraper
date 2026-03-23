import os
import requests
from firecrawl import FirecrawlApp
from notion_client import Client
from datetime import datetime

# [중요] 실제 키를 적지 말고 아래 형식을 유지하세요. 
# 실제 값은 GitHub 웹사이트의 'Secrets'에 이미 입력해두셨으니 서버가 알아서 가져갑니다.
FIRECRAWL_KEY = os.environ.get("FIRECRAWL_API_KEY")
NOTION_TOKEN = os.environ.get("NOTION_TOKEN")
PARENT_PAGE_ID = "32c5baf5994c8060b93ad219d197840e" # KDP 페이지 ID는 공개해도 안전합니다.

notion = Client(auth=NOTION_TOKEN)
app = FirecrawlApp(api_key=FIRECRAWL_KEY)

def run():
    # 1. 아마존 데이터 수집
    scrape_result = app.scrape(
    "https://www.amazon.com/Best-Sellers-Books-Korean-Cooking-Food-Wine/zgbs/books/624448",
    params={
        "extractor": "llm",
        "extraction_prompt": "Extract books with rating 4.5+. Translate summaries into direct Korean (직설스타일). Identify target audience and pricing strategy.",
        "schema": { "items": [{ "title": "str", "author": "str", "rating": "float", "rank": "int", "summary": "str", "img_url": "str", "target": "str", "price_strategy": "str" }] }
            }
        )

    # 2. 노션 DB 생성
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
    for item in scrape_result['items']:
        notion.pages.create(
            parent={"database_id": db_id},
            properties={
                "제목": {"title": [{"text": {"content": item['title']}}]},
                "순위": {"number": item['rank']},
                "요약(한글)": {"rich_text": [{"text": {"content": item['summary']}}]},
                "표지이미지": {"files": [{"name": "Cover", "external": {"url": item['img_url']}}]},
                "타겟/가격전략": {"rich_text": [{"text": {"content": f"타겟: {item['target']}\n전략: {item['price_strategy']}"}}]}
            }
        )
    print(f"완료: {db_title} 생성됨")

if __name__ == "__main__":
    run()