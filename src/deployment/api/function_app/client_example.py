"""Example API client for the Healthcare AI Assistant scoring API.

Acquires an Azure AD access token via the OAuth2 client-credentials flow
(``azure-identity``) and calls ``POST /api/v1/score`` as described in
``docs/api-design.md``.

Usage:
    export AAD_TENANT_ID=...
    export AAD_CLIENT_ID=...
    export AAD_CLIENT_SECRET=...
    export HCAI_API_BASE_URL=https://func-hcai-dev.azurewebsites.net

    python -m src.deployment.api.function_app.client_example
"""

from __future__ import annotations

import os
import uuid

import requests
from azure.identity import ClientSecretCredential

# The API exposes one application permission scope: Score.Invoke
SCOPE = "api://hcai-readmission-api/.default"


def get_access_token() -> str:
    """Acquire an AAD access token via the client-credentials flow."""
    credential = ClientSecretCredential(
        tenant_id=os.environ["AAD_TENANT_ID"],
        client_id=os.environ["AAD_CLIENT_ID"],
        client_secret=os.environ["AAD_CLIENT_SECRET"],
    )
    token = credential.get_token(SCOPE)
    return token.token


def score_encounter(base_url: str, token: str, encounter: dict) -> dict:
    """Call ``POST /api/v1/score`` for a single encounter."""
    request_id = str(uuid.uuid4())
    response = requests.post(
        f"{base_url}/api/v1/score",
        json=encounter,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "x-request-id": request_id,
        },
        timeout=10,
    )
    response.raise_for_status()
    return response.json()


def main() -> None:
    base_url = os.environ.get("HCAI_API_BASE_URL", "http://localhost:7071")
    token = get_access_token()

    example_encounter = {
        "encounter_id": "ENC-100234",
        "age": 72,
        "sex": "F",
        "insurance_type": "Medicare",
        "admission_type": "Emergency",
        "discharge_disposition": "Home",
        "length_of_stay": 5,
        "comorbidity_count": 3,
        "charlson_index": 4,
        "prior_admissions_12mo": 2,
        "prior_ed_visits_12mo": 1,
        "num_medications": 8,
        "bmi": 29.4,
        "systolic_bp": 138,
        "glucose_level": 145,
        "creatinine": 1.1,
    }

    result = score_encounter(base_url, token, example_encounter)
    print(result)


if __name__ == "__main__":
    main()
