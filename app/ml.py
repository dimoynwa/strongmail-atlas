from __future__ import annotations

import streamlit as st


@st.cache_resource
def load_classifier():
    from template_assistant.ml.goemotions import get_classifier

    return get_classifier()


@st.cache_resource
def load_encoder():
    from general_agent.ml.embeddings import get_encoder

    return get_encoder()
