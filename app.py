"""
真人社交模拟智能体 — Streamlit Web UI

运行：
  streamlit run app.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, os.path.dirname(__file__))


def _load_env() -> None:
    try:
        from dotenv import load_dotenv
        project_dir = Path(__file__).resolve().parent
        env_path = project_dir / ".env"
        env_example_path = project_dir / ".env.example"
        if env_path.exists():
            load_dotenv(str(env_path), override=True)
        elif env_example_path.exists():
            load_dotenv(str(env_example_path), override=False)
    except Exception:
        pass


_load_env()

_page_icon_path = os.path.join(os.path.dirname(__file__), "assets", "pig_avatar.png")
page_icon = None
if os.path.exists(_page_icon_path):
    try:
        from PIL import Image
        page_icon = Image.open(_page_icon_path)
    except Exception:
        page_icon = None

st.set_page_config(
    page_title="真人社交模拟智能体",
    page_icon=page_icon or "💬",
    layout="centered",
)

st.title("真人社交模拟智能体")
st.caption("量化关系：高分加分，低分双倍扣分；每轮附带“示例话术”（学习参考，不计入计分）。")

from social_sim import SocialSimEngine  # noqa: E402
from social_sim.formatting import format_turn  # noqa: E402

if "engine" not in st.session_state:
    st.session_state.engine = SocialSimEngine()
if "history" not in st.session_state:
    st.session_state.history = []

with st.sidebar:
    st.subheader("状态")
    engine: SocialSimEngine = st.session_state.engine
    st.metric("当前关系分", engine.state.relationship_score)
    st.metric("累计净积分", engine.state.cumulative_net_points)
    st.metric("轮次", engine.state.turns)
    if st.button("重置对话"):
        st.session_state.engine = SocialSimEngine()
        st.session_state.history = []
        st.rerun()

for item in st.session_state.history:
    with st.chat_message(item["role"]):
        st.markdown(item["content"])

user_text = st.chat_input("输入你的话（输入“退出游戏”结束）")
if user_text:
    st.session_state.history.append({"role": "user", "content": user_text})
    out = st.session_state.engine.step(user_text)
    content = format_turn(out)
    st.session_state.history.append({"role": "assistant", "content": content})
    st.rerun()
