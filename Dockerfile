FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN python data/generate_maintenance_log.py
RUN python -m rul.train
RUN python -m rul.dynamic_train_cli --file data/raw/training/CEO_Schema_100_Pumps_Training.xlsx --config rul/ceo_criteria_config.json

CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port $PORT"]
