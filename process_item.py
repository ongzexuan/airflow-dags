import json
import os
import requests
import psycopg2
import psycopg2.extras
import traceback
import gspread

from datetime import datetime
from dotenv import load_dotenv
from airflow import DAG
from airflow.operators.python_operator import PythonOperator
from airflow.operators.dummy_operator import DummyOperator
from airflow.models import Variable

from slack_operator import task_success_slack_alert, task_fail_slack_alert

load_dotenv()

# Switch variable source depending on deployment environment
ENVIRONMENT = os.getenv("ENVIRONMENT")
if ENVIRONMENT:

    TABLE = os.getenv("TABLE")
    CLIENT_ID = os.getenv("CLIENT_ID")
    SECRET = os.getenv("DEVELOPMENT_SECRET")
    URL = os.getenv("API_HOST") + os.getenv("ENDPOINT")
    PG_HOST = os.getenv("PG_HOST")
    PG_DATABASE = os.getenv("PG_DATABASE")
    PG_PORT = os.getenv("PG_PORT")
    PG_USER = os.getenv("PG_USER")
    PG_PASSWORD = os.getenv("PG_PASSWORD")
    DISCOVER_ACCESS_TOKEN = os.getenv("DISCOVER_ACCESS_TOKEN")
    AMEX_ACCESS_TOKEN = os.getenv("AMEX_ACCESS_TOKEN")
    CITI_ACCESS_TOKEN = os.getenv("CITI_ACCESS_TOKEN")
    CHASE_ACCESS_TOKEN = os.getenv("CHASE_ACCESS_TOKEN")
    CREDENTIALS_FILE = os.getenv("CREDENTIALS_FILE")

else:

    TABLE = Variable.get("TABLE") 
    CLIENT_ID = Variable.get("CLIENT_ID")
    SECRET = Variable.get("DEVELOPMENT_SECRET")
    URL = Variable.get("API_HOST") + Variable.get("ENDPOINT")
    PG_HOST = Variable.get("PG_HOST")
    PG_DATABASE = Variable.get("PG_DATABASE")
    PG_PORT = Variable.get("PG_PORT")
    PG_USER = Variable.get("PG_USER")
    PG_PASSWORD = Variable.get("PG_PASSWORD")
    DISCOVER_ACCESS_TOKEN = Variable.get("DISCOVER_ACCESS_TOKEN")
    AMEX_ACCESS_TOKEN = Variable.get("AMEX_ACCESS_TOKEN")
    CITI_ACCESS_TOKEN = Variable.get("CITI_ACCESS_TOKEN")
    CHASE_ACCESS_TOKEN = Variable.get("CHASE_ACCESS_TOKEN")
    CREDENTIALS_FILE = Variable.get("CREDENTIALS_FILE")


dag_params = {
    "dag_id": "transaction_dag",
    "start_date": datetime(2020, 1, 1),
    "schedule_interval": "59 23 * * *"
}


def process_single_transaction(transaction):
    """
    Takes single Plaid Transaction object and returns a tuple of values that can be exported directly to Postgres.

    :param transaction: JSON object of transaction
    :return: dictionary of required fields for direct export to Postgres
    """

    transaction_id = transaction["transaction_id"]
    pending_transaction_id = transaction["pending_transaction_id"]
    account_id = transaction["account_id"]
    name = transaction["name"]
    amount = transaction["amount"]
    category_id = transaction["category_id"]
    category = transaction["category"]
    date = transaction["date"]
    iso_currency_code = transaction["iso_currency_code"]
    location = json.dumps(transaction["location"])
    payment_channel = transaction["payment_channel"]
    transaction_type = transaction["transaction_type"]
    pending = transaction["pending"]
    payment_reference = transaction["payment_meta"]["reference_number"]
    merchant = transaction["merchant_name"]

    return (transaction_id,
            pending_transaction_id,
            account_id,
            name,
            amount,
            category_id,
            category,
            date,
            iso_currency_code,
            location,
            payment_channel,
            transaction_type,
            pending,
            payment_reference,
            merchant
            )


def process_transactions(plaid_transaction):
    """
    Takes the raw JSON output from the Plaid Transaction API and outputs a list of tuple of the fields being exported to the Postgres database.
    Skips transcations that are marked as pending, we can process it another day.

    :param plaid_transaction: JSON object of the raw JSON output from the Transaction API
    """

    # TODO: do something about Accounts and Items

    collected_transactions = []
    for transaction in plaid_transaction["transactions"]:
        if not transaction["pending"]:
            collected_transactions.append(process_single_transaction(transaction))

    return collected_transactions


def get_transactions(client_id, secret, access_token, start_date, end_date):

    request_body = {
        "client_id": client_id,
        "secret": secret,
        "access_token": access_token,
        "start_date": start_date,
        "end_date": end_date
    }

    r = requests.post(URL,
                      headers={"Content-Type": "application/json"},
                      data=json.dumps(request_body))

    return r.json()


def insert_transactions(rows):

    conn = psycopg2.connect(dbname=PG_DATABASE,
                            user=PG_USER,
                            password=PG_PASSWORD,
                            host=PG_HOST,
                            port=PG_PORT
                            )

    try:
        insert_query = "INSERT INTO {} VALUES %s ON CONFLICT DO NOTHING".format(TABLE)
        template = "(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"
        psycopg2.extras.execute_values(conn.cursor(), insert_query, rows, template=template)
        conn.commit()

    except Exception as ex:
        traceback.print_exc()

    finally:
        conn.close()


def get_db_transactions(date):

    conn = psycopg2.connect(dbname=PG_DATABASE,
                            user=PG_USER,
                            password=PG_PASSWORD,
                            host=PG_HOST,
                            port=PG_PORT
                            )
    results = []

    try:
        select_query = "SELECT * FROM {} WHERE DATE = '{}'".format(TABLE, date)
        curr = conn.cursor()
        curr.execute(select_query)
        results = curr.fetchall()

    except Exception as ex:
        traceback.print_exc()

    finally:
        conn.close()
        return results


def process_discover_transactions(**context):

    # Fail early if the env variable is not present
    assert DISCOVER_ACCESS_TOKEN is not None

    start_date = context["execution_date"].strftime('%Y-%m-%d')
    end_date = context["execution_date"].strftime('%Y-%m-%d')

    data = get_transactions(CLIENT_ID, SECRET, DISCOVER_ACCESS_TOKEN, start_date, end_date)
    rows = process_transactions(data)
    insert_transactions(rows)


def process_amex_transactions(**context):

    # Fail early if the env variable is not present
    assert AMEX_ACCESS_TOKEN is not None

    start_date = context["execution_date"].strftime('%Y-%m-%d')
    end_date = context["execution_date"].strftime('%Y-%m-%d')

    data = get_transactions(CLIENT_ID, SECRET, AMEX_ACCESS_TOKEN, start_date, end_date)
    rows = process_transactions(data)
    insert_transactions(rows)


def process_citi_transactions(**context):

    # Fail early if the env variable is not present
    assert CITI_ACCESS_TOKEN is not None

    start_date = context["execution_date"].strftime('%Y-%m-%d')
    end_date = context["execution_date"].strftime('%Y-%m-%d')

    data = get_transactions(CLIENT_ID, SECRET, CITI_ACCESS_TOKEN, start_date, end_date)
    rows = process_transactions(data)
    insert_transactions(rows)


def process_chase_transactions(**context):

    # Fail early if the env variable is not present
    assert CHASE_ACCESS_TOKEN is not None

    start_date = context["execution_date"].strftime('%Y-%m-%d')
    end_date = context["execution_date"].strftime('%Y-%m-%d')

    data = get_transactions(CLIENT_ID, SECRET, CHASE_ACCESS_TOKEN, start_date, end_date)
    rows = process_transactions(data)
    insert_transactions(rows)


def delete_spreadsheet_rows(worksheet, date):

    rows = worksheet.get_all_records()
    delete_ids = []
    for i, row in enumerate(rows):
        if row['Date'] == date:
            delete_ids.append(i+1)

    for i in reversed(delete_ids):
        worksheet.delete_rows(i+1)


def insert_spreadsheet_rows(worksheet, date, rows):

    def transform_row(datarow):
        return(
            datarow[7].strftime('%Y-%m-%d'),
            datarow[0],
            datarow[1],
            datarow[2],
            datarow[3],
            datarow[4],
            str(datarow[5]),
            ",".join(datarow[6]),
            datarow[8],
            ", ".join([str(v) for v in datarow[9].values() if v]),
            datarow[10],
            datarow[11],
            datarow[12],
            datarow[13] if datarow[13] else "",
            datarow[14]
        )

    for row in rows:
        worksheet.append_row(transform_row(row))


def export_to_gsheet(**context):

    # Get today's date
    today = context["execution_date"].strftime('%Y-%m-%d')

    # Get rows to insert from DB
    rows = get_db_transactions(today)

    # Establish connection to spreadsheet
    gc = gspread.service_account(filename=CREDENTIALS_FILE)
    spreadsheet = gc.open("Tax Year {}".format(context["execution_date"].strftime('%Y')))
    worksheet = spreadsheet.worksheet("Transactions")

    # To maintain idempotency, delete rows from today
    delete_spreadsheet_rows(worksheet, today)

    # Insert rows from today into spreadsheet
    insert_spreadsheet_rows(worksheet, today, rows)



with DAG(**dag_params) as dag:

    # Task: Discover
    discover_task = PythonOperator(task_id="discover_task",
                                   python_callable=process_discover_transactions,
                                   provide_context=True
                                   )

    # Task: Amex
    amex_task = PythonOperator(task_id="amex_task",
                               python_callable=process_amex_transactions,
                               provide_context=True
                               )

    # Task: Citi
    citi_task = PythonOperator(task_id="citi_task",
                               python_callable=process_citi_transactions,
                               provide_context=True
                               )

    # Task: Chase
    chase_task = PythonOperator(task_id="chase_task",
                                python_callable=process_chase_transactions,
                                provide_context=True
                                )

    # Task: Dummy Group
    export_gsheet_task = PythonOperator(task_id="export_to_gsheet_task",
                                        python_callable=export_to_gsheet,
                                        provide_context=True,
                                        on_success_callback=task_success_slack_alert,
                                        on_failure_callback=task_fail_slack_alert)

    discover_task >> export_gsheet_task
    amex_task >> export_gsheet_task
    citi_task >> export_gsheet_task
    chase_task >> export_gsheet_task

