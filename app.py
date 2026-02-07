# ==============================
# 曉臻 · 極速自然能量域（完整版）
# 可直接整份複製貼上
# ==============================

import streamlit as st
import google.generativeai as genai
import os, asyncio, edge_tts, re, base64, io
from PIL import Image

# ---------- 必要套件檢查 ----------
try:
    import fitz  # pymupdf
except ImportError:
    st.error("❌ 缺少 pymupdf，請先安裝")
    st.stop()

# ---------- 頁面設定 ----------
st.set_page_config(
    page_title="臻 · 極速自然能量域",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ---------- 全域 CSS ----------
st.markdown("""
<style>
.stApp { background-color: #ffffff; }
html, body, p, li, h1, h2, h3 {
    font-family: 'HanziPen SC','翩翩體',sans-serif;
    color:#000;
}
.transcript-box {
    border-left: 5px solid #000;
    padding: 14px;
    margin: 12px 0;
    background: #fdfdfd;
}
</style>
""", unsafe_allow_html=True)

st.title("🏃‍♀️ 臻 · 極速自然能量域")
st.markdown("### 🔬 曉臻老師陪你完整跑完一堂自然課")
st.divider()

# ---------- 語音引擎 ----------
async def generate_voice_base64(text: str):
    text = text.replace("---PAGE_SEP---", " ")
    text = re.sub(r'[^\w\u4e00-\u9fff\d，。！？「」～ ]', '', text)
    communicate = edge_tts.Communicate(text, "zh-TW-HsiaoChenNeural", rate="-2%")
    audio = b""
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            audio += chunk["data"]
    b64 = base64.b64encode(audio).decode()
    return f"""
    <audio controls autoplay style="width:100%">
    <source src="data:audio/mp3;base64,{b64}">
    </audio>
    """

# ---------- 顯示稿清洗 ----------
def clean_for_eye(text: str):
    t = text.replace('\u00a0', ' ').replace("---PAGE_SEP---", "")
    t = re.sub(r'\[\[VOICE_START\]\].*?\[\[VOICE_END\]\]', '', t, flags=re.DOTALL)
    t = t.replace("～～", "")
    return t.strip()

# ---------- 側邊欄 ----------
st.sidebar.title("🔑 啟動控制塔")
user_key = st.sidebar.text_input("Google API Key", type="password")

start_page = st.sidebar.number_input("📄 起始頁碼", 1, 200, 1)

# ---------- Session ----------
if "started" not in st.session_state:
    st.session_state.started = False

# ---------- SYSTEM PROMPT（防炸彈版） ----------
SYSTEM_PROMPT = r"""
你是資深自然科學老師「曉臻」。

【強制輸出格式（每一頁都要有）】

---PAGE_SEP---

【知識點總結】
請用考前重點條列。

【曉臻老師上課逐字說明】
請用老師在課堂「慢慢講解」的語氣，
完整解釋概念、圖像、實驗操作，
不少於 200 字。

【常見考點提醒】
請用考試導向提醒學生。

【隱藏讀音稿】
請將所有朗讀內容包在以下標籤中：

[[VOICE_START]]
（所有字母與數字後加～～，化學式轉口語）
[[VOICE_END]]

⚠️ 顯示稿中禁止出現「～～」
⚠️ LaTeX 必須正確，例如：
$$2H_{2}O \\xrightarrow{電解} 2H_{2} + O_{2}$$
"""

# ---------- 主流程 ----------
if not st.session_state.started:

    st.info("📘 請選擇頁碼後開始上課")

    if st.button("🏁 開始上課"):
        if not user_key:
            st.warning("請先輸入 API Key")
            st.stop()

        pdf_path = "data/lecture.pdf"
        if not os.path.exists(pdf_path):
            st.error("❌ 找不到 PDF")
            st.stop()

        with st.spinner("曉臻老師備課中…"):
            doc = fitz.open(pdf_path)

            images = []
            for p in range(start_page-1, min(start_page+3, len(doc))):
                pix = doc.load_page(p).get_pixmap(matrix=fitz.Matrix(2,2))
                images.append(Image.open(io.BytesIO(pix.tobytes())))

            genai.configure(api_key=user_key)
            model = genai.GenerativeModel("models/gemini-2.5-flash")
            res = model.generate_content(
                [SYSTEM_PROMPT] + images
            )

            raw = res.text.replace('\u00a0', ' ')

            voice_blocks = re.findall(
                r'\[\[VOICE_START\]\](.*?)\[\[VOICE_END\]\]',
                raw, re.DOTALL
            )
            voice_text = " ".join(voice_blocks)

            st.session_state.audio = asyncio.run(
                generate_voice_base64(voice_text)
            )
            st.session_state.text = raw
            st.session_state.images = images
            st.session_state.started = True
            st.rerun()

# ---------- 上課畫面 ----------
else:
    st.success("🎓 曉臻老師上課中")

    st.markdown(st.session_state.audio, unsafe_allow_html=True)
    st.divider()

    parts = [
        p for p in st.session_state.text.split("---PAGE_SEP---")
        if p.strip()
    ]

    for idx, img in enumerate(st.session_state.images):
        st.image(img, use_container_width=True)

        if idx < len(parts):
            st.markdown(
                "<div class='transcript-box'><b>📜 曉臻老師逐字稿</b></div>",
                unsafe_allow_html=True
            )
            st.markdown(clean_for_eye(parts[idx]))

        st.divider()

    if st.button("🔁 回到首頁"):
        st.session_state.started = False
        st.rerun()
