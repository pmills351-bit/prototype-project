import streamlit as st
import pandas as pd
import numpy as np

st.set_page_config(page_title='Prototype Dashboard', layout='wide')
st.title('🚀 Prototype Dashboard')
st.caption('Environment: proto311 · NumPy/Pandas quick check')

with st.sidebar:
    st.header('Controls')
    n = st.slider('Rows', 5, 100, 10)
    seed = st.number_input('Random seed', value=42, step=1)

rng = np.random.default_rng(int(seed))
df = pd.DataFrame({
    'a': np.arange(n),
    'b': rng.normal(0, 1, n).round(3),
})

st.subheader('Data Preview')
st.dataframe(df, use_container_width=True)

st.subheader('Summary')
st.write(df.describe())