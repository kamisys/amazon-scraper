import os
from firecrawl import Firecrawl
from notion_client import Client
from datetime import datetime

# GitHub Secrets에서 환경변수 가져오기
FIRECRAWL_KEY = os.environ.get("FIRECRAWL_API_KEY")
NOTION_TOKEN = os.environ.get("NOTION_TOKEN")
PARENT_PAGE_ID = "32c5baf5994c8060b93ad219d197840e"

notion = Client(auth=NOTION_TOKEN)
app = Firecrawl(api_key=FIRECRAWL_KEY)

AMAZON_URL = "https://www.amazon.com/Best-Sellers-Books-Korean-Cooking-Food-Wine/zgbs/books/624448"


def run():
    print("아마존 데이터 수집 시작...")

    result = app.extract(
        [AMAZON_URL],
        prompt=(
            "Extract all books visible on this page. "
            "Include books with rating 4.5 or above. "
            "Translate summaries into direct Korean (직설스타일). "
            "Identify target audience and pricing strategy for each book."
        ),
        schema={
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
    )

    # ✅ 핵심 수정: result는 객체(ExtractResponse)이므로 .get() 대신 .data 사용
    # 그리고 .data도 객체일 수 있으므로 딕셔너리 변환 후 안전하게 꺼냄
    print(f"결과 타입 확인: {type(result)}")  # 디버깅용 - 다음에 또 에러나면 이 줄 보면 됨

    # result.data가 객체면 __dict__로 딕셔너리로 변환, 아니면 그냥 사용
    raw_data = result.data if hasattr(result, 'data') else result

    # raw_data가 딕셔너리인지 객체인지 둘 다 대응
    if isinstance(raw_data, dict):
        data = raw_data.get("items", [])
    elif hasattr(raw_data, 'items') and callable(raw_data.items):
        # 딕셔너리처럼 .items() 메서드가 있는 경우
        data = dict(raw_data).get("items", [])
    else:
        # 객체인 경우 속성으로 접근
        data = getattr(raw_data, 'items', []) or []

    if not data:
        print("수집된 도서 데이터가 없습니다.")
        print(f"원본 결과: {result}")  # 디버깅용
        return

    print(f"수집 완료: {len(data)}건")

    # 노션 데이터베이스 생성
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
    db_id = new_db["id"]

    # 데이터를 노션에 입력
    print(f"노션 입력 중 ({len(data)}건)...")
    for item in data:
        # item이 딕셔너리인지 객체인지 둘 다 대응
        def get_field(obj, key, default="N/A"):
            if isinstance(obj, dict):
                return obj.get(key, default)
            return getattr(obj, key, default)

        img_url = get_field(item, "img_url", "")
        files_value = (
            [{"name": "Cover", "external": {"url": img_url}}]
            if img_url else []
        )

        notion.pages.create(
            parent={"database_id": db_id},
            properties={
                "제목":          {"title":     [{"text": {"content": get_field(item, "title", "N/A")}}]},
                "순위":          {"number":    get_field(item, "rank", 0)},
                "요약(한글)":    {"rich_text": [{"text": {"content": get_field(item, "summary", "요약 없음")}}]},
                "표지이미지":    {"files":     files_value},
                "타겟/가격전략": {"rich_text": [{"text": {"content": (
                    f"타겟: {get_field(item, 'target', 'N/A')}\n"
                    f"전략: {get_field(item, 'price_strategy', 'N/A')}"
                )}}]}
            }
        )

    print(f"완료: {db_title} 생성 및 데이터 입력 완료!")


if __name__ == "__main__":
    run()
