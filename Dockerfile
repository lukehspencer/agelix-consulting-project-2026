FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN python -m rul.dynamic_train_cli \
    --file data/raw/training/CEO_Schema_100_Pumps_Training_v2.xlsx \
    --config rul/ceo_criteria_config.json
RUN python -m rul.dynamic_train_rul2_cli \
    --file data/raw/training/CEO_Schema_100_Pumps_Training_v2.xlsx \
    --config rul/ceo_criteria_config.json

CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port $PORT"]
