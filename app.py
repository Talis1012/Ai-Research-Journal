import streamlit as st

from utils.auth import require_auth


st.set_page_config(
    page_title="Research Journal AI",
    page_icon="🧪",
    layout="wide",
)

require_auth()
st.switch_page("pages/1_Experiments.py")
