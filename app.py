import streamlit as st
import google.generativeai as genai
import os, re, base64, io, asyncio
from PIL import Image

import fitz  # pymupdf
import edge_tts
from mutagen.mp3 import MP3
from streamlit_autorefresh import st_autorefresh


# =========================
# 0) 讀 prompt.txt（避免長 prompt 被截斷）
# =========================
def load_system_prompt(path="prompt.txt"):
    if not os.path.exists(path):
        st.error(f"❌ 找不到 {path}，請建立 prompt.txt 並貼上你的 SYSTEM_PROMPT")
        st.stop()
    with open(path, "r", encoding="utf-8") as f:
        return f.read().strip()

SYSTEM_PROMPT = load_system_prompt("prompt.txt")


# =========================
# 1) Streamlit 風格（保留你白底翩翩體）
# =========================
st.set_page_config(page_title="臻·極速自然能量域", layout="wide", initial_sidebar_state="expanded")
st.markdown("""
<style>
:root { color-scheme: light !important; }
.stApp, [data-testid="stAppViewContainer"], .stMain, [data-testid="stHeader"] { background-color: #ffffff !important; }
div.block-container { padding-top: 1rem !important; padding-bottom: 2rem !important; }
[data-testid="stSidebar"] { min-width: 320px !important; max-width: 320px !important; }
[data-testid="stWidgetLabel"] div, [data-testid="stWidgetLabel"] p { background-color: transparent !important; border: none !important; box-shadow: none !important; padding: 0 !important; }
html, body, .stMarkdown, p, label, li, h1, h2, h3, .stButton button, a {
    color: #000000 !important;
    font-family: 'HanziPen SC', '翩翩體', sans-serif !important;
}
.stButton button { border: 2px solid #000000 !important; background-color: #ffffff !important; font-weight: bold !important; }
.info-box { border: 1px solid #ddd; padding: 1rem; border-radius: 8px; background-color: #f9f9f9; font-size: 0.9rem; color: #000; }
</style>
""", unsafe_allow_html=True)

st.title("🏃‍♀️ 臻 · 極速自然能量域")
st.markdown("### 🔬 資深理化老師 AI 助教：曉臻老師陪你衝刺科學馬拉松")
st.divider()


# =========================
# 2) Async helper
# =========================
def run_async(coro):
    try:
        return asyncio.run(coro)
    except RuntimeError:
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()


# =========================
# 3) 字幕切句（逐句字幕）
# =========================
def split_to_captions(text: str):
    t = re.sub(r"\s+", " ", text.strip())
    chunks = re.split(r"(?<=[。！？；…])\s*", t)
    chunks = [c.strip() for c in chunks if c.strip()]
    return chunks if chunks else [t]


# =========================
# 4) TTS：回傳 audio_html + duration + captions
# =========================
async def generate_voice_and_meta(text: str):
    voice_text = text.replace("---PAGE_SEP---", " ")

    corrections = {"補給": "補己", "Ethanol": "75g", "七十五公克": "乙醇", "75%": "百分之七十五"}
    for word, correct in corrections.items():
        voice_text = voice_text.replace(word, correct)

    clean_text = voice_text.replace("$", "")
    clean_text = clean_text.replace("[[VOICE_START]]", "").replace("[[VOICE_END]]", "")
    clean_text = re.sub(r"[<>#@*_=]", "", clean_text)

    communicate = edge_tts.Communicate(clean_text, "zh-TW-HsiaoChenNeural", rate="-2%")
    audio_data = b""
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            audio_data += chunk["data"]

    duration_sec = MP3(io.BytesIO(audio_data)).info.length
    b64 = base64.b64encode(audio_data).decode()

    audio_html = f"""
    <audio controls autoplay style="width:100%">
      <source src="data:audio/mp3;base64,{b64}" type="audio/mp3">
    </audio>
    """

    captions = split_to_captions(clean_text)
    return audio_html, duration_sec, captions


# =========================
# 5) PDF helpers：載入、取頁圖（預覽用）
# =========================
@st.cache_data(show_spinner=False)
def get_pdf_page_count(pdf_path: str) -> int:
    doc = fitz.open(pdf_path)
    return len(doc)

@st.cache_data(show_spinner=False)
def render_pdf_page_image(pdf_path: str, page_1based: int, zoom: float = 2.0) -> bytes:
    """回傳 PNG bytes，方便 cache（不要 cache PIL 物件）"""
    doc = fitz.open(pdf_path)
    idx = page_1based - 1
    if idx < 0 or idx >= len(doc):
        return b""
    pix = doc.load_page(idx).get_pixmap(matrix=fitz.Matrix(zoom, zoom))
    return pix.tobytes("png")


def png_bytes_to_pil(png_bytes: bytes) -> Image.Image:
    return Image.open(io.BytesIO(png_bytes))


# =========================
# 6) Gemini：產生 顯示稿 + 讀音稿
# =========================
def gemini_generate_page(api_key: str, page_num: int, page_img: Image.Image):
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel("models/gemini-2.5-flash")

    res = model.generate_content([f"{SYSTEM_PROMPT}\n導讀P.{page_num}內容。", page_img])
    raw = (res.text or "").replace("\u00a0", " ").strip()

    voice_matches = re.findall(r"\[\[VOICE_START\]\](.*?)\[\[VOICE_END\]\]", raw, re.DOTALL)
    voice_text = " ".join(m.strip() for m in voice_matches).strip() if voice_matches else raw

    display_text = re.sub(r"\[\[VOICE_START\]\].*?\[\[VOICE_END\]\]", "", raw, flags=re.DOTALL).strip()
    return display_text, voice_text


# =========================
# 7) 準備單頁上課包：PDF + Gemini + TTS
# =========================
def prepare_page_packet(api_key: str, pdf_path: str, page_num: int):
    png = render_pdf_page_image(pdf_path, page_num, zoom=2.0)
    if not png:
        return None
    img = png_bytes_to_pil(png)

    display_text, voice_text = gemini_generate_page(api_key, page_num, img)
    audio_html, duration_sec, captions = run_async(generate_voice_and_meta(voice_text))

    n = max(1, len(captions))
    cap_interval_ms = max(300, int((duration_sec / n) * 1000))  # 最少 0.3 秒，避免刷新太頻繁

    return {
        "page_num": page_num,
        "img": img,
        "display_text": display_text,
        "audio_html": audio_html,
        "captions": captions,
        "cap_interval_ms": cap_interval_ms,
    }


# =========================
# 8) Sidebar：API key + 冊別/章節
# =========================
st.sidebar.title("打開實驗室大門-金鑰")
st.sidebar.markdown("""
<div class="info-box">
<b>上課流程：</b><br>
1) 填 API Key<br>
2) 選冊/章（立刻預覽 PDF）<br>
3) 學生選起始頁<br>
4) 按開始，一次講 5 頁<br>
</div>
""", unsafe_allow_html=True)

api_key = st.sidebar.text_input("🔑 Gemini API Key", type="password")

vol_select = st.sidebar.selectbox("📚 冊別", ["第一冊", "第二冊", "第三冊", "第四冊", "第五冊", "第六冊"], index=3)
chap_select = st.sidebar.selectbox("🧪 章節", ["第一章", "第二章", "第三章", "第四章", "第五章", "第六章"], index=2)

filename = f"{vol_select}_{chap_select}.pdf"
pdf_path = os.path.join("data", filename)


# =========================
# 9) Session state（控制一段 5 頁）
# =========================
if "mode" not in st.session_state:
    st.session_state.mode = "preview"  # preview | teaching | break

if "page_total" not in st.session_state:
    st.session_state.page_total = 0

if "start_page" not in st.session_state:
    st.session_state.start_page = 1

if "end_page" not in st.session_state:
    st.session_state.end_page = 5

if "current_page" not in st.session_state:
    st.session_state.current_page = 1

if "packet" not in st.session_state:
    st.session_state.packet = None

if "cap_idx" not in st.session_state:
    st.session_state.cap_idx = 0

if "cached_api_key" not in st.session_state:
    st.session_state.cached_api_key = ""


# =========================
# 10) 選章節就預覽 PDF（不跑 Gemini / TTS）
# =========================
st.subheader("📄 講義預覽區（選章節即載入）")

if not os.path.exists(pdf_path):
    st.error(f"📂 找不到講義：{filename}（請確認 data/ 內有該 PDF）")
    st.stop()

# 讀總頁數
total_pages = get_pdf_page_count(pdf_path)
st.session_state.page_total = total_pages

colA, colB, colC = st.columns([1, 1, 2])
with colA:
    start_page = st.number_input("🏁 起始頁（本段會講 5 頁）", 1, max(1, total_pages), st.session_state.start_page, key="start_page_ui")
with colB:
    st.write("")
    st.write(f"📌 本段範圍：{start_page} ～ {min(start_page+4, total_pages)}")
with colC:
    st.caption("先讓學生挑頁、看圖，確認後再按開始（避免一直轉圈圈）")

# 同步 session
st.session_state.start_page = int(start_page)
st.session_state.end_page = min(int(start_page) + 4, total_pages)

# 預覽：顯示起始頁（或你想做 5 頁縮圖也可以）
prev_png = render_pdf_page_image(pdf_path, st.session_state.start_page, zoom=1.5)
if prev_png:
    st.image(prev_png, caption=f"預覽：第 {st.session_state.start_page} 頁", use_container_width=True)

st.divider()


# =========================
# 11) 開始上課按鈕（按了才跑 Gemini/TTS）
# =========================
if st.session_state.mode in ["preview", "break"]:
    c1, c2 = st.columns([2, 1])
    with c1:
        start_btn = st.button("🏃‍♀️ 開始上課（一次講 5 頁）", type="primary", use_container_width=True)
    with c2:
        st.button("🏁 回到預覽", use_container_width=True)

    if start_btn:
        if not api_key:
            st.warning("請先輸入 Gemini API Key")
            st.stop()

        st.session_state.cached_api_key = api_key
        st.session_state.current_page = st.session_state.start_page
        st.session_state.cap_idx = 0

        with st.spinner(f"備課中：第 {st.session_state.current_page} 頁（第一次會比較久）..."):
            pkt = prepare_page_packet(api_key, pdf_path, st.session_state.current_page)
            if pkt is None:
                st.error("❌ 讀取頁面失敗（頁碼超出或 PDF 讀取問題）")
                st.stop()

            st.session_state.packet = pkt
            st.session_state.mode = "teaching"
            st.rerun()


# =========================
# 12) 上課模式：逐句字幕 + 自動翻頁 + 到第 5 頁就停
# =========================
if st.session_state.mode == "teaching":
    api_key_use = api_key or st.session_state.cached_api_key
    pkt = st.session_state.packet
    if pkt is None:
        st.session_state.mode = "preview"
        st.rerun()

    st.success(f"🔔 上課中：第 {pkt['page_num']} 頁（本段：{st.session_state.start_page}～{st.session_state.end_page}）")

    st.markdown(pkt["audio_html"], unsafe_allow_html=True)
    st.image(pkt["img"], caption=f"🏁 第 {pkt['page_num']} 頁講義", use_container_width=True)

    # 字幕
    cap_box = st.empty()
    captions = pkt["captions"]
    idx = st.session_state.cap_idx
    if captions:
        line = captions[min(idx, len(captions)-1)]
        cap_box.markdown(
            f"""
            <div style="
                position: sticky; bottom: 0;
                padding: 14px 16px;
                border: 2px solid #000;
                border-radius: 14px;
                background: #fff;
                font-size: 24px;
                text-align: center;
                line-height: 1.4;
                margin-top: 12px;
            ">{line}</div>
            """,
            unsafe_allow_html=True
        )

    # 逐句推進
    st_autorefresh(interval=pkt["cap_interval_ms"], key="caption_tick")
    st.session_state.cap_idx += 1

    # 播完本頁
    if captions and st.session_state.cap_idx >= len(captions):
        next_page = pkt["page_num"] + 1

        # ✅ 到本段第 5 頁結束就停（進 break）
        if next_page > st.session_state.end_page:
            st.session_state.mode = "break"
            st.session_state.packet = None
            st.session_state.cap_idx = 0
            st.rerun()

        # 準備下一頁
        with st.spinner(f"翻頁備課：第 {next_page} 頁..."):
            new_pkt = prepare_page_packet(api_key_use, pdf_path, next_page)
            if new_pkt is None:
                st.error("❌ 下一頁讀取失敗")
                st.session_state.mode = "break"
                st.session_state.packet = None
                st.stop()

            st.session_state.packet = new_pkt
            st.session_state.cap_idx = 0
            st.rerun()

    with st.expander("📜 本頁完整文字稿（顯示稿）"):
        st.markdown(pkt["display_text"])

    if st.button("🏁 強制下課（回到預覽）", use_container_width=True):
        st.session_state.mode = "preview"
        st.session_state.packet = None
        st.session_state.cap_idx = 0
        st.rerun()


# =========================
# 13) 休息模式：提示 + 下一段 5 頁
# =========================
if st.session_state.mode == "break":
    st.success("✅ 本段 5 頁講完囉！休息一下～")
    colx, coly = st.columns([1, 1])

    with colx:
        if st.button("➡️ 下一段 5 頁（繼續上課）", type="primary", use_container_width=True):
            api_key_use = api_key or st.session_state.cached_api_key
            if not api_key_use:
                st.warning("請先輸入 Gemini API Key")
                st.stop()

            next_start = st.session_state.end_page + 1
            if next_start > st.session_state.page_total:
                st.info("已經到最後一頁了。")
                st.session_state.mode = "preview"
                st.rerun()

            st.session_state.start_page = next_start
            st.session_state.end_page = min(next_start + 4, st.session_state.page_total)
            st.session_state.current_page = next_start
            st.session_state.cap_idx = 0

            with st.spinner(f"備課中：第 {next_start} 頁..."):
                pkt = prepare_page_packet(api_key_use, pdf_path, next_start)
                if pkt is None:
                    st.error("❌ 讀取失敗")
                    st.stop()

                st.session_state.packet = pkt
                st.session_state.mode = "teaching"
                st.rerun()

    with coly:
        if st.button("🏁 回到預覽（讓學生重新選頁）", use_container_width=True):
            st.session_state.mode = "preview"
            st.session_state.packet = None
            st.session_state.cap_idx = 0
            st.rerun()
