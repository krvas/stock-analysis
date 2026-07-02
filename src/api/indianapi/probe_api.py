"""
Runs the IndianAPI client against the real API to verify that it can fetch data and parse it into the expected schema.
"""

import os
import argparse
from dotenv import load_dotenv


from src.api.indianapi.client import IndianAPIClient



def main(name: str):
    load_dotenv()  # Load environment variables from .env file
    api_key = os.getenv("INDIAN_API_KEY")
    if not api_key:
        raise ValueError("INDIAN_API_KEY environment variable is not set.")
    Client = IndianAPIClient(api_key=api_key)
    Client.fetch_company(name)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--name", required=True)
    args = parser.parse_args()
    main(args.name)