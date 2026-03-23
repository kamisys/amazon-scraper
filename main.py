import os
import requests
from firecrawl import FirecrawlApp
from notion_client import Client
from datetime import datetime

# GitHub Secrets에서 환경변수 로드
FIRECRAWL_KEY = "fc-da0184068e4b4555b7682d89e733fdc4"
NOTION_TOKEN = "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"
DATABASE_ID = "32c5baf5994c8060b93ad219d197840e"

notion = Client(auth=NOTION_TOKEN)
app = FirecrawlApp(api_key=FIRECRAWL_KEY)

def get_last_week_rank():
    # 지난주 데이터를 조회하여 제목별 순위를 딕셔너리로 반환 (순위 변동 계산용)
    results = notion.databases.query(database_id=DATABASE_ID).get("results")
    return {res["properties"]["제목"]["title"][0]["text"]["content"]: res["properties"]["순위"]["number"] 
            for res in results if res["properties"]["제목"]["title"]}

def scrape_and_upload():
    last_ranks = get_last_week_rank()
    
    # 1. Firecrawl로 데이터 추출 및 한국어 번역 요청
    # 시스템 프롬프트에 '직설스타일' 번역 지시 포함 가능
    scrape_result = app.scrape_url(
        "https://www.amazon.com/Best-Sellers-Kindle-Store-Korean-Cooking-Food-Wine/zgbs/digital-text/157488011",
        params={
            "extractor": "llm",
            "extraction_prompt": "Extract books with rating 4.5+. Translate summaries into direct, concise Korean (직설스타일).",
            "schema": { "items": [{ "title": "str", "author": "str", "rating": "float", "rank": "int", "summary": "str", "img_url": "str" }] }
        }
    )

    for item in scrape_result['items']:
        # 2. 순위 변동 계산
        prev_rank = last_ranks.get(item['title'])
        diff = f"NEW" if not prev_rank else (f"▲{prev_rank - item['rank']}" if prev_rank > item['rank'] else f"▼{item['rank'] - prev_rank}")
        if prev_rank == item['rank']: diff = "-"

        # 3. 노션 페이지 생성 (파일 업로드는 URL 전달 방식 사용)
        notion.pages.create(
            parent={"database_id": DATABASE_ID},
            properties={
                "제목": {"title": [{"text": {"content": item['title']}}]},
                "순위변동": {"rich_text": [{"text": {"content": diff}}]},
                "요약(한글)": {"rich_text": [{"text": {"content": item['summary']}}]},
                "평점": {"number": item['rating']},
                "표지이미지": {"files": [{"name": "Cover", "external": {"url": item['img_url']}}]},
                "수집날짜": {"date": {"start": datetime.now().isoformat()}}
            }
        )

if __name__ == "__main__":
    scrape_and_upload()