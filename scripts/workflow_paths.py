from datetime import datetime
from pathlib import Path


OUTPUT_DIR = Path("output")
VALID_PURPOSES = {"sale", "rent"}


def normalize_purpose(purpose):
    value = (purpose or "sale").strip().lower()

    if value not in VALID_PURPOSES:
        raise ValueError(f"Purpose must be one of: {', '.join(sorted(VALID_PURPOSES))}")

    return value


def prompt_for_purpose(default="sale"):
    default = normalize_purpose(default)

    while True:
        answer = input(f"Listing purpose [sale/rent] (default: {default}): ").strip().lower()

        if not answer:
            return default

        if answer in VALID_PURPOSES:
            return answer

        print("Please enter 'sale' or 'rent'.")


def purpose_dir(purpose):
    return OUTPUT_DIR / normalize_purpose(purpose)


def urls_file(purpose):
    return purpose_dir(purpose) / "property_urls.json"


def raw_dir(purpose):
    return purpose_dir(purpose) / "raw"


def processed_dir(purpose):
    return purpose_dir(purpose) / "processed"


def predicted_dir(purpose):
    return purpose_dir(purpose) / "predicted"


def logs_dir(purpose):
    return purpose_dir(purpose) / "logs"


def master_file(purpose):
    return purpose_dir(purpose) / "listing_details_master.csv"


def price_history_file(purpose):
    return purpose_dir(purpose) / "price_history.csv"


def timestamp():
    return datetime.now().strftime("%Y-%m-%d_%H-%M")


def ensure_purpose_dirs(purpose):
    base_dir = purpose_dir(purpose)

    for path in [
        base_dir,
        raw_dir(purpose),
        processed_dir(purpose),
        predicted_dir(purpose),
        logs_dir(purpose),
    ]:
        path.mkdir(parents=True, exist_ok=True)
