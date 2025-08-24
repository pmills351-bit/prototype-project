import streamlit as st, requests

st.title("Iris Predictor (API + ONNX)")
port = 8001  # match your uvicorn port

a = st.number_input("sepal_len", 0.0, 10.0, 5.1, 0.1)
b = st.number_input("sepal_wid", 0.0, 10.0, 3.5, 0.1)
c = st.number_input("petal_len", 0.0, 10.0, 1.4, 0.1)
d = st.number_input("petal_wid", 0.0, 10.0, 0.2, 0.1)

if st.button("Predict"):
    r = requests.post(f"http://127.0.0.1:{port}/predict", json={
        "sepal_len": a, "sepal_wid": b, "petal_len": c, "petal_wid": d
    })
    st.write("Response:", r.json())