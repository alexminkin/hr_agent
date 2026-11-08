FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN python -m playwright install --with-deps chromium
COPY hr_agent ./hr_agent
CMD ["uvicorn", "hr_agent.api:app", "--host", "0.0.0.0", "--port", "8000"]
