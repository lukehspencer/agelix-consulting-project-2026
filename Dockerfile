FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN python data/generate_maintenance_log.py
RUN python -m rul.train
RUN python -c "import pandas as pd, os; os.makedirs('data/raw/uploads', exist_ok=True); tel = pd.read_excel('data/raw/telemetry/KSB_Calio_Predictive_Maintenance_Complete.xlsx'); log = pd.read_excel('data/raw/maintenance/maintenance_log.xlsx'); w = pd.ExcelWriter('data/raw/uploads/KSB_Full_Upload.xlsx'); tel.to_excel(w, sheet_name='Operational Telemetry', index=False); log.to_excel(w, sheet_name='Failure & Maintenance Logs', index=False); w.close()"
RUN python -m rul.dynamic_train_cli --file data/raw/uploads/KSB_Full_Upload.xlsx --config rul/ksb_criteria_config.json

CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port $PORT"]
