"""Data ingestion.

In production, raw encounter data is landed in the ``raw`` zone of the data
lake (``abfss://raw@sthcai<env>001.dfs.core.windows.net/encounters/``) by an
Azure Data Factory pipeline that copies from the source EHR/claims systems on
a daily schedule.

For local development, demos, and CI, this module *simulates* that ingestion
by generating a synthetic but schema-conformant batch of inpatient encounter
records (see ``src/common/schemas.py:RawEncounter``).

Usage:
    python -m src.data_pipeline.ingest --output data/raw/encounters.csv --rows 5000
"""

from __future__ import annotations

import argparse
from datetime import date, timedelta

import numpy as np
import pandas as pd

from src.common.logging_utils import get_logger
from src.common.utils import set_seed, timer, write_table

logger = get_logger(__name__)

SEX_VALUES = ["M", "F", "U"]
SEX_WEIGHTS = [0.48, 0.50, 0.02]

ETHNICITY_VALUES = ["Group A", "Group B", "Group C", "Group D"]
ETHNICITY_WEIGHTS = [0.40, 0.30, 0.20, 0.10]

INSURANCE_VALUES = ["Medicare", "Medicaid", "Commercial", "SelfPay"]
INSURANCE_WEIGHTS = [0.45, 0.20, 0.30, 0.05]

ADMISSION_TYPE_VALUES = ["Elective", "Emergency", "Urgent"]
ADMISSION_TYPE_WEIGHTS = [0.25, 0.55, 0.20]

DISCHARGE_DISPOSITION_VALUES = ["Home", "SNF", "Rehab", "HomeHealth", "AMA"]
DISCHARGE_DISPOSITION_WEIGHTS = [0.60, 0.15, 0.10, 0.12, 0.03]

DIAGNOSIS_CODES = ["I50.9", "J44.1", "E11.9", "N18.3", "I63.9", "K70.30", "F32.9"]


@timer
def generate_synthetic_encounters(n_rows: int, start_date: date, seed: int = 42) -> pd.DataFrame:
    """Generate a synthetic batch of inpatient encounter records.

    The generator approximates realistic correlations (e.g., higher
    comorbidity and prior utilization increase readmission probability) so
    downstream feature engineering, training, and responsible AI modules
    have meaningful signal to work with.
    """
    set_seed(seed)
    rng = np.random.default_rng(seed)

    age = rng.integers(0, 101, size=n_rows)
    sex = rng.choice(SEX_VALUES, size=n_rows, p=SEX_WEIGHTS)
    ethnicity = rng.choice(ETHNICITY_VALUES, size=n_rows, p=ETHNICITY_WEIGHTS)
    insurance_type = rng.choice(INSURANCE_VALUES, size=n_rows, p=INSURANCE_WEIGHTS)
    admission_type = rng.choice(ADMISSION_TYPE_VALUES, size=n_rows, p=ADMISSION_TYPE_WEIGHTS)
    discharge_disposition = rng.choice(
        DISCHARGE_DISPOSITION_VALUES, size=n_rows, p=DISCHARGE_DISPOSITION_WEIGHTS
    )

    length_of_stay = np.clip(rng.poisson(4, size=n_rows), 0, 60)
    comorbidity_count = np.clip(rng.poisson(2, size=n_rows), 0, 12)
    charlson_index = np.clip(comorbidity_count * rng.uniform(0.5, 1.5, size=n_rows), 0, 15)
    prior_admissions_12mo = np.clip(rng.poisson(0.6, size=n_rows), 0, 10)
    prior_ed_visits_12mo = np.clip(rng.poisson(0.8, size=n_rows), 0, 15)
    num_medications = np.clip(rng.poisson(5, size=n_rows), 0, 25)

    bmi = np.clip(rng.normal(28, 6, size=n_rows), 12, 60)
    systolic_bp = np.clip(rng.normal(128, 18, size=n_rows), 80, 220)
    glucose_level = np.clip(rng.normal(110, 35, size=n_rows), 50, 450)
    creatinine = np.clip(rng.normal(1.0, 0.5, size=n_rows), 0.3, 8.0)

    # Admit dates spread across the prior 12 months; discharge >= admit.
    admit_offsets = rng.integers(0, 365, size=n_rows)
    admit_dates = [start_date - timedelta(days=int(o)) for o in admit_offsets]
    discharge_dates = [
        admit_dates[i] + timedelta(days=int(length_of_stay[i])) for i in range(n_rows)
    ]

    primary_diagnosis_code = rng.choice(DIAGNOSIS_CODES, size=n_rows)

    # Synthetic readmission risk: logistic function of key risk drivers.
    risk_score = (
        0.35 * (prior_admissions_12mo / 3.0)
        + 0.30 * (prior_ed_visits_12mo / 4.0)
        + 0.25 * (charlson_index / 10.0)
        + 0.10 * (num_medications >= 5).astype(float)
        + 0.05 * (discharge_disposition == "SNF").astype(float)
        + 0.05 * (admission_type == "Emergency").astype(float)
        - 0.10 * (age < 18).astype(float)
        + rng.normal(0, 0.15, size=n_rows)
    )
    probability = 1 / (1 + np.exp(-(risk_score - 0.6) * 4))
    readmitted_30d = (rng.uniform(size=n_rows) < probability).astype(int)

    df = pd.DataFrame(
        {
            "encounter_id": [f"ENC-{100000 + i}" for i in range(n_rows)],
            "patient_id": [f"PAT-{rng.integers(10000, 99999)}" for _ in range(n_rows)],
            "admit_date": admit_dates,
            "discharge_date": discharge_dates,
            "age": age,
            "sex": sex,
            "ethnicity": ethnicity,
            "insurance_type": insurance_type,
            "admission_type": admission_type,
            "discharge_disposition": discharge_disposition,
            "length_of_stay": length_of_stay,
            "primary_diagnosis_code": primary_diagnosis_code,
            "comorbidity_count": comorbidity_count,
            "charlson_index": charlson_index.round(2),
            "prior_admissions_12mo": prior_admissions_12mo,
            "prior_ed_visits_12mo": prior_ed_visits_12mo,
            "num_medications": num_medications,
            "bmi": bmi.round(1),
            "systolic_bp": systolic_bp.round(0),
            "glucose_level": glucose_level.round(0),
            "creatinine": creatinine.round(2),
            "readmitted_30d": readmitted_30d,
        }
    )

    logger.info(
        "generated_synthetic_encounters",
        extra={"rows": len(df), "readmission_rate": float(df["readmitted_30d"].mean())},
    )
    return df


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate/ingest raw encounter data.")
    parser.add_argument("--output", required=True, help="Output path (.csv or .parquet)")
    parser.add_argument("--rows", type=int, default=5000, help="Number of rows to generate")
    parser.add_argument("--seed", type=int, default=42, help="Random seed")
    args = parser.parse_args()

    df = generate_synthetic_encounters(n_rows=args.rows, start_date=date.today(), seed=args.seed)
    write_table(df, args.output)


if __name__ == "__main__":
    main()
