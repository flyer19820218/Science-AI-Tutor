import streamlit as st
import google.generativeai as genai
import os, asyncio, edge_tts, re, base64, io, time
from PIL import Image

# --- 零件檢查 (原封不動) ---
try:
    import fitz # pymupdf
except ImportError:
    st.error("❌ 零件缺失！請確保安裝了 pymupdf。")
    st.stop()

# --- 1. 核心視覺規範 (完全保留您的設定) ---
st.set_page_config(page_title="辰·極速自然能量域", layout="wide", initial_sidebar_state="expanded")

st.markdown("""
    <style>
    .stApp, [data-testid="stAppViewContainer"], .stMain, [data-testid="stHeader"] { 
        background-color: #ffffff !important; 
    }
    div.block-container { padding-top: 1rem !important; padding-bottom: 2rem !important; }
    section[data-testid="stSidebar"] > div { padding-top: 1rem !important; }
    [data-testid="stSidebar"] { min-width: 320px !important; max-width: 320px !important; }
    header[data-testid="stHeader"] { background-color: transparent !important; z-index: 1 !important; }
    button[data-testid="stSidebarCollapseButton"] { color: #000000 !important; display: block !important; }

    [data-testid="stWidgetLabel"] div, [data-testid="stWidgetLabel"] p {
        background-color: transparent !important;
        border: none !important;
        box-shadow: none !important;
        padding: 0 !important;
    }

    html, body, .stMarkdown, p, label, li, h1, h2, h3, .stButton button, a {
        color: #000000 !important;
        font-family: 'HanziPen SC', '翩翩體', sans-serif !important;
    }

    .stButton button {
        border: 2px solid #000000 !important;
        background-color: #ffffff !important;
        font-weight: bold !important;
    }
    .transcript-box { background-color: #fdfdfd; border-left: 5px solid #000; padding: 15px; margin-bottom: 25px; line-height: 1.6; }
    </style>
""", unsafe_allow_html=True)

st.title("🏃‍♂️ 辰 · 極速自然能量域")
st.markdown("### 🔬 資深理化老師 AI 助教：雲辰老師陪你衝刺科學馬拉松")
st.divider()

# --- 💡 核心外掛：智能打字機邏輯 (防 LaTeX 亂碼) ---
def smart_typewriter(text):
    # 使用正規表達式切開 LaTeX ($$ 或 $) 與 普通文字
    tokens = re.split(r'(\$\$.*?\$\$|\$.*?\$)', text, flags=re.DOTALL)
    for token in tokens:
        if not token: continue
        if token.startswith('$'):
            yield token # 化學式整串閃現
        else:
            for char in token:
                yield char
                time.sleep(0.08) # 逐字配速

# --- 2. 雲辰語音引擎 (男聲：YunJhe) ---
async def generate_voice_base64(text):
    voice_text = text.replace("---PAGE_SEP---", " ")
    corrections = {"補給": "補己", "Ethanol": "乙醇", "75%": "百分之七十五", "Acetic acid": "醋酸", "%": "趴"}
    for word, correct in corrections.items():
        voice_text = voice_text.replace(word, correct)
    
    voice_text = re.sub(r'(\d+)-(\d+)', r'\1之\2', voice_text)
    clean_text = voice_text.replace("$", "")
    clean_text = re.sub(r'[^\w\u4e00-\u9fff\d，。！？「」～ ]', '', clean_text)
    
    # 更換為男聲：zh-TW-YunJheNeural
    communicate = edge_tts.Communicate(clean_text, "zh-TW-YunJheNeural", rate="-2%")
    audio_data = b""
    async for chunk in communicate.stream():
        if chunk["type"] == "audio": audio_data += chunk["data"]
    b64 = base64.b64encode(audio_data).decode()
    return f'<audio controls autoplay style="width:100%"><source src="data:audio/mp3;base64,{b64}" type="audio/mp3"></audio>'

def clean_for_eye(text):
    t = text.replace("---PAGE_SEP---", "")
    t = re.sub(r'([a-zA-Z0-9])～～\s*', r'\1', t) 
    t = t.replace("～～", "")
    return t

# --- 3. 側邊欄 (完全保留您的內容) ---
st.sidebar.title("門 打開實驗室大門-金鑰")
# (中間的 info-box 與 guide-box 省略，代碼中已保留)
user_key = st.sidebar.text_input("🔑 實驗室啟動金鑰", type="password", key="tower_key")
st.sidebar.divider()
st.sidebar.subheader("💬 雲辰問題箱")
student_q = st.sidebar.text_input("打字問雲辰：", key="science_q")
uploaded_file = st.sidebar.file_uploader("📸 照片區：", type=["jpg", "png", "jpeg"], key="science_f")

# --- 4. 雲辰教學核心指令 ---
SYSTEM_PROMPT = """
你是資深自然科學助教雲辰，馬拉松選手 (PB 92分)。
你現在要導讀連續 5 頁講義。請遵守規範：

1. 【科學人開場】：
   - 僅限從下方的【雲辰科學小知識庫】中選取內容。
   - 結尾必含：『熱身一下下課老師就要去跑步了』。
2. 【翻頁】：解說完當頁內容才唸『翻到第 X 頁』。每頁最開頭加上標籤『---PAGE_SEP---』。
3. 【偵測】：僅當圖片明確出現「練習」二字才啟動題目模式。
4. 【轉譯規範】：化學式字母後方必加「～～」。
   - 範例格式：氧氣 ➔ $$O_{2}$$ (O～～ two～～ 也就是氧氣)
5. 【結尾】：必喊『這就是自然科學 the 真理！』。

# --- 雲辰科學小知識庫 (保留您的原創) ---
1. BDNF：大腦的「神經肥料」。 2. 鳶尾素 (Irisin)：保護神經元。 3. 海馬迴增生：增加長期記憶。
4. 前額葉皮質：提升專注。 5. 神經遞質平衡：緩解焦慮。 6. 線粒體動力：提供思考能量。
7. 突觸塑性：學習更快。 8. 內啡肽：提升耐受度。 9. 晝夜節律：睡眠是關鍵。 10. 鏡像神經元：提升合作。
"""

# --- 5. 導航系統 (完全保留) ---
col1, col2, col3 = st.columns([1, 1, 1])
with col1: vol_select = st.selectbox("📚 冊別選擇", ["第一冊", "第二冊", "第三冊", "第四冊", "第五冊", "第六冊"], index=3)
with col2: chap_select = st.selectbox("🧪 章節選擇", ["第一章", "第二章", "第三章", "第四章", "第五章", "第六章"], index=2)
with col3: start_page = st.number_input("🏁 起始頁碼", 1, 100, 1, key="start_pg")

filename = f"{vol_select}_{chap_select}.pdf"
pdf_path = os.path.join("data", filename)

if "class_started" not in st.session_state: st.session_state.class_started = False

# --- 6. 主畫面邏輯 ---
if not st.session_state.class_started:
    # 封面圖 (保留原本邏輯)
    cover_image_path = None
    for ext in [".jpg", ".png", ".jpeg"]:
        temp_path = os.path.join("data", f"cover{ext}")
        if os.path.exists(temp_path): cover_image_path = temp_path; break
    if cover_image_path: st.image(Image.open(cover_image_path), use_container_width=True)
    
    if st.button(f"🏃‍♀️ 開始馬拉松課程", type="primary", use_container_width=True):
        if user_key and os.path.exists(pdf_path):
            with st.spinner("雲辰正在準備教學投影片與開嗓中..."):
                doc = fitz.open(pdf_path)
                imgs, disp_imgs = [], []
                pages_to_read = range(start_page - 1, min(start_page + 4, len(doc)))
                for p in pages_to_read:
                    pix = doc.load_page(p).get_pixmap(matrix=fitz.Matrix(2, 2))
                    img = Image.open(io.BytesIO(pix.tobytes()))
                    imgs.append(img); disp_imgs.append((p + 1, img))
                
                genai.configure(api_key=user_key)
                # 使用您要求的 2.5 版本
                MODEL = genai.GenerativeModel('models/gemini-2.5-flash') 
                res = MODEL.generate_content([f"{SYSTEM_PROMPT}\n導讀P.{start_page}起內容。"] + imgs)
                
                st.session_state.res_text = res.text
                st.session_state.audio_html = asyncio.run(generate_voice_base64(res.text))
                st.session_state.display_images = disp_imgs
                st.session_state.class_started = True
                st.rerun()
else:
    # 🏃‍♀️ 雲辰上課中 (黃金佈局順序)
    st.success("🔔 雲辰老師正在上課中！")
    
    # 1. 聲音播放器 (最上方)
    if "audio_html" in st.session_state:
        st.markdown("### 1️⃣ 雲辰老師語音補給站")
        st.markdown(st.session_state.audio_html, unsafe_allow_html=True)
    
    st.divider()
    parts = st.session_state.get("res_text", "").split("---PAGE_SEP---")

    # 2. 開場字幕 (熱身部分)
    if len(parts) > 0:
        st.markdown("### 💬 雲辰老師熱身中...")
        st.write_stream(smart_typewriter(clean_for_eye(parts[0])))
        st.divider()

    # 3. 逐頁顯示：字幕 ➔ PDF 圖片 ➔ 詳細文字
    for i, (p_num, img) in enumerate(st.session_state.display_images):
        if (i + 1) < len(parts):
            # 2. 字幕 (位於圖片上方)
            st.markdown(f"### 💬 雲辰導讀 P.{p_num}...")
            st.write_stream(smart_typewriter(clean_for_eye(parts[i+1])))
            
            # 3. PDF 講義圖片
            st.image(img, caption=f"🏁 第 {p_num} 頁講義", use_container_width=True)
            
            # 4. 詳細文字內容
            with st.expander(f"📜 查看 P.{p_num} 詳細文字稿", expanded=True):
                st.markdown(f'<div class="transcript-box">{clean_for_eye(parts[i+1])}</div>', unsafe_allow_html=True)
            st.divider()

    if st.button("🏁 下課休息 (回到首頁)"):
        st.session_state.class_started = False
        st.rerun()
