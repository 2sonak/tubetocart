import streamlit as st
import re
import json
import urllib.parse
from youtube_transcript_api import YouTubeTranscriptApi
from google import genai
from google.genai import types

# -----------------------------------------------------------------------------
# 1. 페이지 기본 설정
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="TubeToCart - 유튜브 레시피 1초 장보기",
    page_icon="🛒",
    layout="centered"
)

st.title("🛒 TubeToCart (T2C)")
st.caption("유튜브 요리 영상 URL만 넣으면, 집에 없는 재료만 쏙 골라 쿠팡으로 넘겨드립니다.")

# -----------------------------------------------------------------------------
# 2. 사이드바 - 설정값 (Gemini API Key & 쿠팡 파트너스 코드)
# -----------------------------------------------------------------------------
with st.sidebar:
    st.header("⚙️ 서비스 설정")
    gemini_api_key = st.text_input("Google Gemini API Key", type="password", help="AIStudio에서 발급받은 AIzaSy... 키를 입력하세요.")
    tracking_code = st.text_input("쿠팡 파트너스 Tracking Code", value="AF1234567", help="본인의 파트너스 추적 코드를 입력하세요.")
    st.divider()
    st.info("💡 API Key는 카드 등록 없이 100% 무료로 사용할 수 있습니다.")

# -----------------------------------------------------------------------------
# 3. 핵심 헬퍼 함수
# -----------------------------------------------------------------------------
def extract_video_id(url: str) -> str:
    """유튜브 URL에서 11자리 Video ID를 추출"""
    pattern = r"(?:v=|\/|embed\/|shorts\/)([0-9A-Za-z_-]{11})"
    match = re.search(pattern, url)
    return match.group(1) if match else None

def get_ingredients_from_gemini(transcript_text: str, api_key: str):
    """유튜브 자막을 Gemini API에 던져 재료 JSON 추출"""
    client = genai.Client(api_key=api_key)
    
    prompt = f"""
    너는 요리 레시피 전문 분석가다. 
    아래 유튜브 영상 자막에서 [요리 이름]과 [필요한 재료 목록 및 용량]만 추출해라.
    
    자막 내용:
    {transcript_text[:5000]}
    """
    
    # JSON 형식 강제 출력 설정
    response = client.models.generate_content(
        model='gemini-2.5-flash',
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema={
                "type": "OBJECT",
                "properties": {
                    "recipe_name": {"type": "STRING"},
                    "ingredients": {
                        "type": "ARRAY",
                        "items": {
                            "type": "OBJECT",
                            "properties": {
                                "name": {"type": "STRING"},
                                "amount": {"type": "STRING"}
                            },
                            "required": ["name", "amount"]
                        }
                    }
                },
                "required": ["recipe_name", "ingredients"]
            }
        )
    )
    
    return json.loads(response.text)

def make_coupang_search_url(keyword: str, tracking_code: str) -> str:
    """재료명을 쿠팡 파트너스 검색 URL 규격으로 변환"""
    encoded_keyword = urllib.parse.quote(keyword)
    return f"https://www.coupang.com/np/search?component=&q={encoded_keyword}&channel=user&subid={tracking_code}"

# -----------------------------------------------------------------------------
# 4. 세션 관리 및 메인 UI
# -----------------------------------------------------------------------------
if "parsed_data" not in st.session_state:
    st.session_state.parsed_data = None

url_input = st.text_input("🎥 유튜브 영상 주소를 입력하세요:", placeholder="https://www.youtube.com/watch?v=...")

if st.button("🚀 재료 추출하기", type="primary"):
    if not gemini_api_key:
        st.error("사이드바에 Gemini API Key를 먼저 입력해 주세요!")
    elif not url_input:
        st.warning("유튜브 URL을 입력해 주세요.")
    else:
        video_id = extract_video_id(url_input)
        if not video_id:
            st.error("올바른 유튜브 URL 형식이 아닙니다.")
        else:
            with st.spinner("유튜브 자막을 읽고 Gemini가 재료를 추출하는 중..."):
                try:
                    # 1) 자막 추출
                    transcript_list = YouTubeTranscriptApi.get_transcript(video_id, languages=['ko'])
                    full_text = " ".join([item['text'] for item in transcript_list])
                    
                    # 2) Gemini AI 파싱
                    data = get_ingredients_from_gemini(full_text, gemini_api_key)
                    st.session_state.parsed_data = data
                    st.success("재료 추출 완료!")
                    
                except Exception as e:
                    st.error(f"오류 발생: 자막이 없는 영상이거나 API 키가 올바르지 않습니다. ({str(e)})")

# -----------------------------------------------------------------------------
# 5. 결과 출력 및 쿠팡 파트너스 구매 연동
# -----------------------------------------------------------------------------
if st.session_state.parsed_data:
    data = st.session_state.parsed_data
    
    st.divider()
    st.subheader(f"🍳 요리명: {data.get('recipe_name', '추출된 레시피')}")
    st.write("집에 **없는 재료만 체크**한 뒤 구매 버튼을 누르세요:")

    selected_ingredients = []
    
    # 재료 체크박스 출력
    for idx, item in enumerate(data.get("ingredients", [])):
        label = f"{item['name']} ({item['amount']})"
        is_checked = st.checkbox(label, value=True, key=f"ing_{idx}")
        if is_checked:
            selected_ingredients.append(item['name'])

    st.divider()

    # 구매 버튼 생성
    if selected_ingredients:
        st.write(f"🛒 **구매할 재료 ({len(selected_ingredients)}개):** {', '.join(selected_ingredients)}")
        
        cols = st.columns(min(len(selected_ingredients), 3))
        for i, ingredient in enumerate(selected_ingredients):
            col_idx = i % 3
            link = make_coupang_search_url(ingredient, tracking_code)
            cols[col_idx].link_button(f"📦 {ingredient} 쿠팡 검색", link, use_container_width=True)
            
    else:
        st.info("선택된 재료가 없습니다. 모두 집에 있군요! 🎉")

# -----------------------------------------------------------------------------
# 6. 법적 필수 고지 문구
# -----------------------------------------------------------------------------
st.divider()
st.caption("⚠️ **법적 고지:** 이 서비스는 쿠팡 파트너스 활동의 일환으로, 이에 따른 일정액의 수수료를 제공받습니다.")
