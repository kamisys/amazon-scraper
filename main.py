import os
from firecrawl import Firecrawl          # ✅ 신버전 클래스명
from notion_client import Client
from datetime import datetime

# GitHub Secrets에서 환경변수 가져오기
FIRECRAWL_KEY = os.environ.get("FIRECRAWL_API_KEY")
NOTION_TOKEN = os.environ.get("NOTION_TOKEN")
PARENT_PAGE_ID = "32c5baf5994c8060b93ad219d197840e"  # KDP 페이지 ID

# 클라이언트 객체 생성
notion = Client(auth=NOTION_TOKEN)
app = Firecrawl(api_key=FIRECRAWL_KEY)   # ✅ 신버전 클래스명

# 수집할 아마존 URL
AMAZON_URL = "https://www.amazon.com/Best-Sellers-Books-Korean-Cooking-Food-Wine/zgbs/books/624448"


def run():
    print("아마존 데이터 수집 시작...")

    # ✅ 핵심 수정: scrape() 안에 extract를 넣지 않고, extract() 메서드를 별도로 사용
    # extract()는 URL 목록과 프롬프트/스키마를 받아서 구조화된 데이터를 돌려줌
    result = app.extract(
        [AMAZON_URL],          # URL을 리스트로 넘김 (여러 개도 가능)
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
                            "title":          {"type": "string"},   # 책 제목
                            "author":         {"type": "string"},   # 저자명
                            "rating":         {"type": "number"},   # 평점 (예: 4.7)
                            "rank":           {"type": "integer"},  # 베스트셀러 순위
                            "summary":        {"type": "string"},   # 한글 요약
                            "img_url":        {"type": "string"},   # 표지 이미지 URL
                            "target":         {"type": "string"},   # 타겟 독자층
                            "price_strategy": {"type": "string"}    # 가격 전략 분석
                        }
                    }
                }
            }
        }
    )

    # ✅ extract() 결과에서 데이터 꺼내기
    # result는 딕셔너리 형태: {"success": True, "data": {"items": [...]}}
    if not result or not result.get("data"):
        print("데이터 수집 실패: Firecrawl 응답이 비어있습니다.")
        return

    data = result["data"].get("items", [])

    # 데이터가 없으면 경고 출력 후 종료
    if not data:
        print("수집된 도서 데이터가 없습니다. 페이지 구조가 바뀌었을 수 있습니다.")
        return

    print(f"수집 완료: {len(data)}건")

    # 2. 노션 데이터베이스 생성
    print("노션 데이터베이스 생성 중...")
    db_title = f"Korean food 베스트셀러-{datetime.now().strftime('%Y%m%d')}"

    new_db = notion.databases.create(
        parent={"type": "page_id", "page_id": PARENT_PAGE_ID},
        title=[{"type": "text", "text": {"content": db_title}}],
        properties={
            "제목":          {"title": {}},      # 책 제목 (메인 컬럼)
            "순위":          {"number": {}},     # 베스트셀러 순위
            "요약(한글)":    {"rich_text": {}},  # 한글 요약
            "표지이미지":    {"files": {}},      # 표지 이미지
            "타겟/가격전략": {"rich_text": {}}   # 타겟 독자 + 가격 전략
        }
    )
    db_id = new_db["id"]  # 새로 만든 DB의 고유 ID

    # 3. 데이터를 노션에 한 건씩 입력
    print(f"노션 입력 중 ({len(data)}건)...")
    for item in data:
        # 이미지 URL이 없으면 빈 리스트로 처리 (노션 오류 방지)
        img_url = item.get("img_url", "")
        files_value = (
            [{"name": "Cover", "external": {"url": img_url}}]
            if img_url else []
        )

        notion.pages.create(
            parent={"database_id": db_id},
            properties={
                "제목":          {"title":     [{"text": {"content": item.get("title", "N/A")}}]},
                "순위":          {"number":    item.get("rank", 0)},
                "요약(한글)":    {"rich_text": [{"text": {"content": item.get("summary", "요약 없음")}}]},
                "표지이미지":    {"files":     files_value},
                "타겟/가격전략": {"rich_text": [{"text": {"content": (
                    f"타겟: {item.get('target', 'N/A')}\n"
                    f"전략: {item.get('price_strategy', 'N/A')}"
                )}}]}
            }
        )

    print(f"완료: {db_title} 생성 및 데이터 입력 완료!")


if __name__ == "__main__":
    run()
