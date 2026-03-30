FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY td_generator.py replay_server.py ./

EXPOSE 9000

CMD ["uvicorn", "replay_server:app", "--host", "0.0.0.0", "--port", "9000"]
