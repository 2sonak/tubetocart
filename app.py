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
# 2. 사이드바 - 설정값
# -----------------------------------------------------------------------------
default_key = st.secrets.get("GEMINI_API_KEY", "")

with st.sidebar:
    st.header("⚙️ 서비스 설정")
    gemini_api_key = st.text_input(
        "Google Gemini API Key", 
        value=default_key, 
        type="password", 
        help="AIStudio에서 발급받은 AIzaSy... 키를 입력하세요."
    )
    tracking_code = st.text_input(
        "쿠팡 파트너스 Tracking Code", 
        value="AF1234567", 
        help="본인의 파트너스 추적 코드를 입력하세요."
    )
    st.divider()
    st.info("💡 Gemini API Key는 카드 등록 없이 100% 무료로 사용할 수 있습니다.")

# -----------------------------------------------------------------------------
# 3. 핵심 헬퍼 함수
# -----------------------------------------------------------------------------
def extract_video_id(url: str) -> str:
    pattern = r"(?:v=|\/|embed\/|shorts\/)([0-9A-Za-z_-]{11})"
    match = re.search(pattern, url)
    return match.group(1) if match else None

def fetch_youtube_transcript(video_id: str) -> str:
    try:
        api = YouTubeTranscriptApi()
        if hasattr(api, "fetch"):
            fetched = api.fetch(video_id, languages=['ko', 'en'])
            return " ".join([item.text if hasattr(item, 'text') else item['text'] for item in fetched])
        elif hasattr(api, "list"):
            transcript_list = api.list(video_id)
            transcript = transcript_list.find_transcript(['ko', 'en'])
            fetched = transcript.fetch()
            return " ".join([item.text if hasattr(item, 'text') else item['text'] for item in fetched])
    except Exception:
        pass

    try:
        if hasattr(YouTubeTranscriptApi, "get_transcript"):
            transcript_data = YouTubeTranscriptApi.get_transcript(video_id, languages=['ko', 'en'])
            return " ".join([item['text'] for item in transcript_data])
    except Exception:
        pass

    try:
        if hasattr(YouTubeTranscriptApi, "list_transcripts"):
            transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
            for t in transcript_list:
                fetched = t.fetch()
                return " ".join([item['text'] if isinstance(item, dict) else item.text for item in fetched])
    except Exception:
        pass

    raise Exception("자막을 불러올 수 없습니다. 해당 영상에 자막이 제공되지 않습니다.")

def get_ingredients_from_gemini(transcript_text: str, api_key: str):
    """현재 서버에 살아있는 최신 모델을 자동 감지하여 추출"""
    client = genai.Client(api_key=api_key)
    
    prompt = f"""
    너는 요리 레시피 전문 분석가다. 
    아래 유튜브 영상 자막에서 [요리 이름]과 [필요한 재료 목록 및 용량]만 추출해라.
    
    반드시 아래 포맷의 JSON 형식으로만 응답해야 한다:
    {{
        "recipe_name": "요리 이름",
        "ingredients": [
            {{"name": "돼지고기", "amount": "300g"}},
            {{"name": "양파", "amount": "1개"}}
        ]
    }}
    
    자막 내용:
    {transcript_text[:5000]}
    """
    
    # 1. 2026년 현재 구글 서버에 '실제로 살아있는' 모델 목록을 직접 물어봐서 가져옴
    available_models = []
    try:
        for m in client.models.list():
            name = m.name.replace("models/", "") if hasattr(m, 'name') else str(m)
            # 텍스트 생성용 Flash 모델만 필터링
            if "flash" in name.lower() and "embed" not in name.lower():
                available_models.append(name)
    except Exception as e:
        raise Exception(f"구글 서버에서 최신 모델 목록을 가져오지 못했습니다: {str(e)}")
        
    if not available_models:
        raise Exception("현재 API 키로 사용할 수 있는 Flash 모델이 없습니다. 구글 정책이 변경되었을 수 있습니다.")
        
    last_error = None
    
    # 2. 살아있는 최신 모델들을 위에서부터 순서대로 찔러봄 (하나만 성공하면 됨)
    for model_name in available_models:
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json"
                )
            )
            return json.loads(response.text)
        except Exception as e:
            last_error = str(e)
            continue
            
    # 3. 만약 다 실패했다면, 대체 어떤 모델을 찔러봤고 왜 실패했는지 화면에 친절하게 띄워줌
    raise Exception(f"추출 실패. 살아있는 최신 모델들({', '.join(available_models)})을 모두 시도했지만 막혔습니다. 마지막 에러: {last_error}")

def make_coupang_search_url(keyword: str, tracking_code: str) -> str:
    encoded_keyword = urllib.parse.quote(keyword)
    return f"https://www.coupang.com/np/search?component=&q={encoded_keyword}&channel=user&subid={tracking_code}"

# -----------------------------------------------------------------------------
# 4. 메인 UI 로직
# -----------------------------------------------------------------------------
if "parsed_data" not in st.session_state:
    st.session_state.parsed_data = None

url_input = st.text_input("🎥 유튜브 영상 주소를 입력하세요:", placeholder="https://www.youtube.com/watch?v=... 또는 shorts URL")

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
            with st.spinner("구글 최신 AI 모델을 감지하고 재료를 추출하는 중..."):
                try:
                    full_text = fetch_youtube_transcript(video_id)
                    data = get_ingredients_from_gemini(full_text, gemini_api_key)
                    st.session_state.parsed_data = data
                    st.success("재료 추출 완료!")
                except Exception as e:
                    st.error(f"오류 발생: {str(e)}")

# -----------------------------------------------------------------------------
# 5. 결과 출력 파트
# -----------------------------------------------------------------------------
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

st.divider()
st.caption("⚠️ **법적 고지:** 이 서비스는 쿠팡 파트너스 활동의 일환으로, 이에 따른 일정액의 수수료를 제공받습니다.")
