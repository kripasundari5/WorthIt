FROM python:3.12-slim
WORKDIR /app
COPY ui/requirements.txt /app/ui/requirements.txt
RUN pip install --no-cache-dir -i https://pypi.org/simple -r /app/ui/requirements.txt
COPY core /app/core
COPY ui /app/ui
EXPOSE 8501
CMD ["streamlit", "run", "ui/app.py", "--server.address=0.0.0.0", "--server.port=8501"]
