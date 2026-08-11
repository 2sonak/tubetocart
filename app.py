import streamlit as st
import re
import json
import urllib.parse
from youtube_transcript_api import YouTubeTranscriptApi
from openai import OpenAI

# 1. 페이지 기본 설정
st.set_page_config(
    page_title="TubeToCart - 유튜브 레시피 1초 장보기",
    page_icon="🛒",
    layout="centered"
)

st.title("🛒 TubeToCart (T2C)")
st.caption("유튜브 요리 영상 URL만 넣으면, 집에 없는 재료만 쏙 골라 쿠팡으로 넘겨드립니다.")

# 2. 사이드바 설정
with st.sidebar:
    st.header("⚙️ 서비스 설정")
    openai_api_key = st.text_input("OpenAI API Key", type="password", help="sk-... 로 시작하는 키를 입력하세요.")
    tracking_code = st.text_input("쿠팡 파트너스 Tracking Code", value="AF1234567", help="본인의 파트너스 추적 코드를 입력하세요.")
    st.divider()
    st.info("💡 API Key는 서버에 저장되지 않고 메모리상에서만 일회성으로 사용됩니다.")

# 3. 핵심 헬퍼 함수
def extract_video_id(url: str) -> str:
    pattern = r"(?:v=|\/|embed\/|shorts\/)([0-9A-Za-z_-]{11})"
    match = re.search(pattern, url)
    return match.group(1) if match else None

def get_ingredients_from_ai(transcript_text: str, api_key: str):
    client = OpenAI(api_key=api_key)
    prompt = """
    너는 요리 레시피 전문 분석가다. 
    아래 유튜브 영상 자막에서 [요리 이름]과 [필요한 재료 목록 및 용량]만 추출해라.
    
    반드시 아래 JSON 포맷으로만 응답해야 한다. 추가 설명은 일절 배제해라:
    {
        "recipe_name": "요리 이름",
        "ingredients": [
            {"name": "돼지고기", "amount": "300g"},
            {"name": "양파", "amount": "1개"}
        ]
    }
    """
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": prompt},
            {"role": "user", "content": transcript_text[:4000]}
        ],
        response_format={"type": "json_object"}
    )
    return json.loads(response.choices[0].message.content)

def make_coupang_search_url(keyword: str, tracking_code: str) -> str:
    encoded_keyword = urllib.parse.quote(keyword)
    return f"https://www.coupang.com/np/search?component=&q={encoded_keyword}&channel=user&subid={tracking_code}"

# 4. 세션 관리 및 UI
if "parsed_data" not in st.session_state:
    st.session_state.parsed_data = None

url_input = st.text_input("🎥 유튜브 영상 주소를 입력하세요:", placeholder="https://www.youtube.com/watch?v=...")

if st.button("🚀 재료 추출하기", type="primary"):
    if not openai_api_key:
        st.error("사이드바에 OpenAI API Key를 먼저 입력해 주세요!")
    elif not url_input:
        st.warning("유튜브 URL을 입력해 주세요.")
    else:
        video_id = extract_video_id(url_input)
        if not video_id:
            st.error("올바른 유튜브 URL 형식이 아닙니다.")
        else:
            with st.spinner("유튜브 자막을 읽고 AI가 재료를 추출하는 중..."):
                try:
                    transcript_list = YouTubeTranscriptApi.get_transcript(video_id, languages=['ko'])
                    full_text = " ".join([item['text'] for item in transcript_list])
                    data = get_ingredients_from_ai(full_text, openai_api_key)
                    st.session_state.parsed_data = data
                    st.success("재료 추출 완료!")
                except Exception as e:
                    st.error(f"오류 발생: 자막이 없는 영상이거나 API 키가 올바르지 않습니다. ({str(e)})")

# 5. 결과 출력 및 버튼
if st.session_state.parsed_data:
    data = st.session_state.parsed_data
    st.divider()
    st.subheader(f"🍳 요리명: {data.get('recipe_name', '추출된 레시피')}")
    st.write("집에 **없는 재료만 체크**한 뒤 구매 버튼을 누르세요:")

    selected_ingredients = []
    for idx, item in enumerate(data.get("ingredients", [])):
        label = f"{item['name']} ({item['amount']})"
        is_checked = st.checkbox(label, value=True, key=f"ing_{idx}")
        if is_checked:
            selected_ingredients.append(item['name'])

    st.divider()
    if selected_ingredients:
        st.write(f"🛒 **구매할 재료 ({len(selected_ingredients)}개):** {', '.join(selected_ingredients)}")
        cols = st.columns(min(len(selected_ingredients), 3))
        for i, ingredient in enumerate(selected_ingredients):
            col_idx = i % 3
            link = make_coupang_search_url(ingredient, tracking_code)
            cols[col_idx].link_button(f"📦 {ingredient} 쿠팡 검색", link, use_container_width=True)
    else:
        st.info("선택된 재료가 없습니다. 모두 집에 있군요! 🎉")

# 6. 법적 필수 고지 문구
st.divider()
st.caption("⚠️ **법적 고지:** 이 서비스는 쿠팡 파트너스 활동의 일환으로, 이에 따른 일정액의 수수료를 제공받습니다.")
