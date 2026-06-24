from pathlib import Path
from datetime import datetime, timedelta
import uuid

import pandas as pd
import numpy as np

OUTPUT_PATH = Path(__file__).parent / "raw" / "maintenance" / "maintenance_log.xlsx"
TELEMETRY_PATH = Path(__file__).parent / "raw" / "telemetry" / "KSB_Calio_Predictive_Maintenance_Complete.xlsx"


def generate_pump_synthetic_data(num_pumps=10, days_of_history=365):
    telemetry_records = []
    maintenance_records = []
    np.random.seed(42)
    start_date = datetime(2026, 1, 1)
    pump_ids = ["KSB-CALIO-3040-1000", "KSB-CALIO-3040-1001",
                "KSB-CALIO-3040-1002", "KSB-CALIO-3040-1003",
                "KSB-CALIO-3040-1004"]
    for p in range(num_pumps):
        pump_id = pump_ids[p]
        bearing_wear_rate = np.random.uniform(0.5, 2.5)
        electronics_wear_rate = np.random.uniform(0.7, 1.8)
        cumulative_hours = 0.0
        bearing_health = 100.0
        electronics_health = 100.0
        is_failed = False
        for day in range(days_of_history):
            if is_failed:
                break
            current_time = start_date + timedelta(days=day)
            fluid_temp = 20.0 + 15.0 * np.sin(2 * np.pi * day / 365) + np.random.normal(0, 2)
            fluid_temp = np.clip(fluid_temp, -10.0, 110.0)
            speed_rpm = np.random.choice([1200, 1800, 2400, 2850], p=[0.2, 0.5, 0.2, 0.1]) + np.random.normal(0, 50)
            speed_rpm = np.clip(speed_rpm, 1000, 2900)
            mains_voltage = np.random.normal(230, 5)
            if np.random.rand() < 0.01:
                mains_voltage += np.random.choice([-25, 25])
            base_current = (speed_rpm / 2900.0) * 0.85
            current_a = np.clip(base_current + np.random.normal(0, 0.03), 0.15, 0.91)
            winding_temp = fluid_temp + (current_a * 35) + np.random.normal(0, 1)
            spm_temp = 30.0 + (current_a * 40) + (0.2 * fluid_temp) + np.random.normal(0, 2)
            cumulative_hours += np.random.uniform(22.0, 24.0)
            bearing_damage = (speed_rpm / 2900.0) * (1 if fluid_temp < 90 else 2.5) * 0.05 * bearing_wear_rate
            bearing_health -= bearing_damage
            electronics_damage = (spm_temp / 80.0) * (2 if abs(mains_voltage - 230) > 20 else 1) * 0.04 * electronics_wear_rate
            electronics_health -= electronics_damage
            vibration_score = np.random.exponential(scale=0.2) + (100.0 - bearing_health) * 0.1
            failed_comp = None
            root_cause = None
            if bearing_health <= 0:
                is_failed = True
                failed_comp = "Bearings"
                root_cause = "Mechanical_Wear"
            elif electronics_health <= 0 or spm_temp > 105:
                is_failed = True
                failed_comp = "Electronics"
                root_cause = "Thermal_Overload"
            elif winding_temp > 115:
                is_failed = True
                failed_comp = "Motor_Winding"
                root_cause = "Insulation_Breakdown"
            telemetry_records.append({
                "Pump_ID": pump_id,
                "Timestamp": current_time,
                "Operating_Hours": round(cumulative_hours, 1),
                "Speed_RPM": round(speed_rpm, 0),
                "Current_A": round(current_a, 2),
                "Winding_Temp_C": round(winding_temp, 1),
                "SPM_Temp_C": round(spm_temp, 1),
                "Mains_Voltage": round(mains_voltage, 1),
                "Fluid_Temp_C": round(fluid_temp, 1),
                "Vibration_Score": round(vibration_score, 3),
                "True_RUL_Days": np.nan
            })
            if is_failed:
                maintenance_records.append({
                    "Log_ID": f"LOG-{uuid.uuid4().hex[:4].upper()}",
                    "Pump_ID": pump_id,
                    "Event_Timestamp": current_time,
                    "Event_Type": "Failure",
                    "Failed_Component": failed_comp,
                    "Root_Cause": root_cause
                })
    df_telemetry = pd.DataFrame(telemetry_records)
    df_maintenance = pd.DataFrame(maintenance_records)
    for pid in df_telemetry["Pump_ID"].unique():
        max_time = df_telemetry[df_telemetry["Pump_ID"] == pid]["Timestamp"].max()
        pump_mask = df_telemetry["Pump_ID"] == pid
        df_telemetry.loc[pump_mask, "True_RUL_Days"] = (
            max_time - df_telemetry.loc[pump_mask, "Timestamp"]
        ).dt.days
    return df_telemetry, df_maintenance


if __name__ == "__main__":
    pump_ids = ["KSB-CALIO-3040-1000", "KSB-CALIO-3040-1001",
                "KSB-CALIO-3040-1002", "KSB-CALIO-3040-1003",
                "KSB-CALIO-3040-1004"]

    df_ops, df_logs = generate_pump_synthetic_data(
        num_pumps=5,
        days_of_history=1095
    )

    for pump_id in pump_ids:
        pump_rows = df_ops[df_ops["Pump_ID"] == pump_id]
        for pm_day in range(90, len(pump_rows), 90):
            maintenance_date = pump_rows.iloc[pm_day - 1]["Timestamp"]
            df_logs = pd.concat([df_logs, pd.DataFrame([{
                "Log_ID": f"LOG-{uuid.uuid4().hex[:4].upper()}",
                "Pump_ID": pump_id,
                "Event_Timestamp": maintenance_date,
                "Event_Type": "Maintenance",
                "Failed_Component": "None",
                "Root_Cause": "Scheduled_PM"
            }])], ignore_index=True)

    df_logs = df_logs.sort_values("Event_Timestamp").reset_index(drop=True)

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    df_logs.to_excel(OUTPUT_PATH, index=False)

    print(f"Saved {len(df_logs)} maintenance log rows to {OUTPUT_PATH}")
    print()
    event_counts = df_logs["Event_Type"].value_counts()
    for event_type, count in event_counts.items():
        print(f"  {event_type}: {count}")
    print()
    print("Breakdown by Pump_ID:")
    breakdown = df_logs.groupby(["Pump_ID", "Event_Type"]).size().unstack(fill_value=0)
    print(breakdown.to_string())

    TELEMETRY_PATH.parent.mkdir(parents=True, exist_ok=True)
    df_ops.rename(columns={"Timestamp": "Date"}, inplace=True)
    with pd.ExcelWriter(TELEMETRY_PATH, engine="openpyxl") as writer:
        df_ops.to_excel(writer, sheet_name="Operational Telemetry", index=False)
        pd.DataFrame().to_excel(writer, sheet_name="Summary Dashboard", index=False)

    print(f"\nSaved {len(df_ops)} telemetry rows to {TELEMETRY_PATH}")
    print("Rows per pump:")
    print(df_ops["Pump_ID"].value_counts().sort_index().to_string())
