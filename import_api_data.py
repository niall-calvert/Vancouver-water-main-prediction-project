import requests
import psycopg2
import json


# Distribution main data:
# https://opendata.vancouver.ca/api/explore/v2.1/catalog/datasets/water-distribution-mains/records?limit=20

# Transmission main data:
# https://opendata.vancouver.ca/api/explore/v2.1/catalog/datasets/water-transmission-mains/records?limit=20

# 311 data from 2009:
# https://opendata.vancouver.ca/api/explore/v2.1/catalog/datasets/3-1-1-service-requests-2009-2021/records?limit=20&refine=department%3A%22ENG%20-%20Waterworks%20Operations%22&refine=service_request_type%3A%22Water%20Leak%20Case%22&refine=closure_reason%3A%22Service%20provided%22&refine=closure_reason%3A%22Dispatched%20to%20Crew%22

# 311 data from 2021:
# https://opendata.vancouver.ca/api/explore/v2.1/catalog/datasets/3-1-1-service-requests/records?limit=20&refine=service_request_type%3A%22Water%20Leak%20Case%22&refine=closure_reason%3A%22Dispatched%20to%20Crew%22&refine=closure_reason%3A%22Service%20provided%22&refine=department%3A%22ENG%20-%20Waterworks%20Operations%22


DATASETS = [
    {
        "table_name": "raw_distribution_mains",
        "url": "https://opendata.vancouver.ca/api/explore/v2.1/catalog/datasets/water-distribution-mains/records?limit=20"
    },
    {
        "table_name": "raw_transmission_mains",
        "url": "https://opendata.vancouver.ca/api/explore/v2.1/catalog/datasets/water-transmission-mains/records?limit=20"
    },
    {
        "table_name": "raw_311_water_leaks_2009_2021",
        "url": "https://opendata.vancouver.ca/api/explore/v2.1/catalog/datasets/3-1-1-service-requests-2009-2021/records?limit=20&refine=department%3A%22ENG%20-%20Waterworks%20Operations%22&refine=service_request_type%3A%22Water%20Leak%20Case%22&refine=closure_reason%3A%22Service%20provided%22&refine=closure_reason%3A%22Dispatched%20to%20Crew%22"
    },
    {
        "table_name": "raw_311_water_leaks_2021_present",
        "url": "https://opendata.vancouver.ca/api/explore/v2.1/catalog/datasets/3-1-1-service-requests/records?limit=20&refine=service_request_type%3A%22Water%20Leak%20Case%22&refine=closure_reason%3A%22Dispatched%20to%20Crew%22&refine=closure_reason%3A%22Service%20provided%22&refine=department%3A%22ENG%20-%20Waterworks%20Operations%22"
    }
]


conn = psycopg2.connect(
    host="localhost",
    port=5432,
    dbname="apidata",
    user="myuser",
    password="mypassword"
)

cursor = conn.cursor()


for dataset in DATASETS:
    table_name = dataset["table_name"]
    url = dataset["url"]

    print(f"Importing {table_name}...")

    cursor.execute(f"""
        CREATE TABLE IF NOT EXISTS {table_name} (
            id SERIAL PRIMARY KEY,
            raw_json JSONB,
            imported_at TIMESTAMPTZ DEFAULT NOW()
        );
    """)

    response = requests.get(url)
    response.raise_for_status()

    data = response.json()
    records = data["results"]

    for record in records:
        cursor.execute(f"""
            INSERT INTO {table_name} (
                raw_json
            )
            VALUES (%s);
        """, (
            json.dumps(record),
        ))

    conn.commit()

    print(f"Imported {len(records)} records into {table_name}.")


cursor.close()
conn.close()

print("Done importing all datasets.")