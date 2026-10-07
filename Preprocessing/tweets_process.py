import json
from datetime import datetime

from tqdm import tqdm


def normalize_twitter_date(date_text):
    try:
        parsed_date = datetime.strptime(date_text, "%a %b %d %H:%M:%S %z %Y")
        return parsed_date.strftime("%Y-%m-%d")
    except Exception:
        return date_text


def normalize_doi(doi_text):
    if not doi_text:
        return ""
    if doi_text.startswith("https://"):
        return doi_text
    if doi_text.startswith("doi.org/") or doi_text.startswith("doi.org"):
        return f"https://{doi_text}"
    return f"https://doi.org/{doi_text}"


def load_input_records(input_file):
    with open(input_file, "r", encoding="utf-8") as file:
        return json.load(file)


def build_output_records(records):
    output_records = []
    for item in tqdm(records, desc="Processing tweets"):
        output_item = {}
        if "link" in item:
            output_item["tweets_link"] = item["link"]
        if "tweet_id" in item:
            output_item["tweet_id"] = item["tweet_id"]
        if "Xdoi" in item:
            output_item["doi"] = normalize_doi(item["Xdoi"])
        if "published_time" in item:
            output_item["published_time"] = normalize_twitter_date(item["published_time"])
        output_records.append(output_item)
    return output_records


def save_output_records(records, output_file):
    with open(output_file, "w", encoding="utf-8") as file:
        json.dump(records, file, ensure_ascii=False, indent=2)


def process_tweets(input_file, output_file):
    print("Loading input records")
    input_records = load_input_records(input_file)
    print(f"Input records: {len(input_records)}")

    output_records = build_output_records(input_records)
    print(f"Output records: {len(output_records)}")

    save_output_records(output_records, output_file)
    print("Completed")


def main():
    input_file = "tweets_by_doi.json"
    output_file = "tweets_by_doi_processed.json"
    process_tweets(input_file, output_file)


if __name__ == "__main__":
    main()

