FROM python:3.11-slim
WORKDIR /app
COPY . /app
RUN pip install --no-cache-dir -r requirements.txt || true
EXPOSE 8501 8000
CMD ["bash", "-lc", "streamlit run app_streamlit_audit_pilot.py"]
