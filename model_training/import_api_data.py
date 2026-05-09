import json
import requests
import psycopg2
from psycopg2.extras import execute_batch


# Distribution main data:
# https://opendata.vancouver.ca/api/explore/v2.1/catalog/datasets/water-distribution-mains/exports/json

# Transmission main data:
# https://opendata.vancouver.ca/api/explore/v2.1/catalog/datasets/water-transmission-mains/exports/json

# 311 data from 2009:
# https://opendata.vancouver.ca/api/explore/v2.1/catalog/datasets/3-1-1-service-requests-2009-2021/exports/json?where=department%3D%22ENG%20-%20Waterworks%20Operations%22%20AND%20service_request_type%3D%22Water%20Leak%20Case%22%20AND%20%28closure_reason%3D%22Service%20provided%22%20OR%20closure_reason%3D%22Dispatched%20to%20Crew%22%29

# 311 data from 2021:
# https://opendata.vancouver.ca/api/explore/v2.1/catalog/datasets/3-1-1-service-requests/exports/json?where=department%3D%22ENG%20-%20Waterworks%20Operations%22%20AND%20service_request_type%3D%22Water%20Leak%20Case%22%20AND%20%28closure_reason%3D%22Service%20provided%22%20OR%20closure_reason%3D%22Dispatched%20to%20Crew%22%29


DATASETS = [
    {
        "table_name": "raw_distribution_mains",
        "url": "https://opendata.vancouver.ca/api/explore/v2.1/catalog/datasets/water-distribution-mains/exports/json",
    },
    {
        "table_name": "raw_transmission_mains",
        "url": "https://opendata.vancouver.ca/api/explore/v2.1/catalog/datasets/water-transmission-mains/exports/json",
    },
    {
        "table_name": "raw_311_water_leaks_2009_2021",
        "url": "https://opendata.vancouver.ca/api/explore/v2.1/catalog/datasets/3-1-1-service-requests-2009-2021/exports/json?where=department%3D%22ENG%20-%20Waterworks%20Operations%22%20AND%20service_request_type%3D%22Water%20Leak%20Case%22%20AND%20%28closure_reason%3D%22Service%20provided%22%20OR%20closure_reason%3D%22Dispatched%20to%20Crew%22%29",
    },
    {
        "table_name": "raw_311_water_leaks_2021_present",
        "url": "https://opendata.vancouver.ca/api/explore/v2.1/catalog/datasets/3-1-1-service-requests/exports/json?where=department%3D%22ENG%20-%20Waterworks%20Operations%22%20AND%20service_request_type%3D%22Water%20Leak%20Case%22%20AND%20%28closure_reason%3D%22Service%20provided%22%20OR%20closure_reason%3D%22Dispatched%20to%20Crew%22%29",
    },
]


def extract_records(data, table_name):
    """
    Supports both:
    - exports/json endpoint, which usually returns a list
    - records endpoint, which usually returns {"results": [...]}
    """
    if isinstance(data, list):
        return data

    if isinstance(data, dict) and "results" in data:
        return data["results"]

    raise ValueError(
        f"Unexpected API response format for {table_name}. "
        f"Expected list or dict with 'results', got {type(data)}"
    )


conn = psycopg2.connect(
    host="localhost",
    port=5432,
    dbname="apidata",
    user="myuser",
    password="mypassword",
)

cursor = conn.cursor()

try:
    for dataset in DATASETS:
        table_name = dataset["table_name"]
        url = dataset["url"]

        print(f"Importing {table_name}...")

        # Drop and recreate so old sample rows do not remain.
        cursor.execute(f"""
            DROP TABLE IF EXISTS {table_name};

            CREATE TABLE {table_name} (
                id SERIAL PRIMARY KEY,
                raw_json JSONB,
                imported_at TIMESTAMPTZ DEFAULT NOW()
            );
        """)

        response = requests.get(url, timeout=120)
        response.raise_for_status()

        data = response.json()
        records = extract_records(data, table_name)

        rows = [(json.dumps(record),) for record in records]

        execute_batch(
            cursor,
            f"""
            INSERT INTO {table_name} (raw_json)
            VALUES (%s);
            """,
            rows,
            page_size=1000,
        )

        conn.commit()

        print(f"Imported {len(records)} records into {table_name}.")

except Exception as error:
    conn.rollback()
    print(f"Import failed: {error}")
    raise

finally:
    cursor.close()
    conn.close()

print("Done importing all datasets.")