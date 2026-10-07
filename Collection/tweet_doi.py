import argparse
import json
import os
import shutil
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from threading import Lock
import requests
from tqdm import tqdm

BASE_URL = "https://api.twitterapi.io"
API_ENDPOINT = "/twitter/tweet/advanced_search"
API_KEY_ENV_NAME = "TWITTERAPI_IO_KEY"
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
INPUT_JSON = os.path.join(SCRIPT_DIR, "works_ai_with_doi.json")
OUTPUT_JSON = os.path.join(SCRIPT_DIR, "tweets_by_doi.json")
PROGRESS_FILE = os.path.join(SCRIPT_DIR, "doi_search_progress.json")
BATCH_SIZE = 2000
MAX_WORKERS = 16
QPS_LIMIT = 20
_rate_lock = Lock()
_request_times = []
_api_error_detected = False
_api_error_lock = Lock()
_api_error_message = ""


def init_rate_limiter():
    global _request_times
    with _rate_lock:
        _request_times = []


def set_api_error(message):
    global _api_error_detected, _api_error_message
    with _api_error_lock:
        _api_error_detected = True
        _api_error_message = message


def get_api_error():
    with _api_error_lock:
        return _api_error_detected, _api_error_message


def wait_for_rate_limit():
    global _request_times
    with _rate_lock:
        current_time = time.time()
        _request_times = [t for t in _request_times if current_time - t < 1.0]
        if len(_request_times) >= QPS_LIMIT:
            oldest_time = min(_request_times)
            wait_time = 1.0 - (current_time - oldest_time) + 0.01
            if wait_time > 0:
                time.sleep(wait_time)
                current_time = time.time()
                _request_times = [t for t in _request_times if current_time - t < 1.0]
        _request_times.append(current_time)


def get_api_key():
    api_key = os.getenv(API_KEY_ENV_NAME, "").strip()
    return api_key


def build_request_headers():
    return {"X-API-Key": get_api_key()}


def search_tweets_by_doi(doi, cursor=None, retry_count=0):
    url = f"{BASE_URL}{API_ENDPOINT}"
    headers = build_request_headers()
    query = f'"{doi}"'
    params = {"queryType": "Latest", "query": query}
    if cursor:
        params["cursor"] = cursor

    wait_for_rate_limit()

    try:
        response = requests.get(url, headers=headers, params=params, timeout=30)

        if response.status_code == 200:
            return response.json()

        if response.status_code == 401:
            error_msg = "API authentication failed (401): invalid or expired API key"
            print(f"\nError: {error_msg}")
            set_api_error(error_msg)
            return None

        if response.status_code == 402:
            error_data = response.json() if response.text else {}
            error_msg = (
                "API credit error (402): "
                f"{error_data.get('message', 'Credits are not enough. Please recharge')}"
            )
            print(f"\nError: {error_msg}")
            set_api_error(error_msg)
            return None

        if response.status_code == 403:
            error_msg = "API access denied (403): expired account or insufficient permission"
            print(f"\nError: {error_msg}")
            set_api_error(error_msg)
            return None

        if response.status_code == 429:
            wait_time = 2.0
            if retry_count < 3:
                time.sleep(wait_time)
                return search_tweets_by_doi(doi, cursor, retry_count + 1)
            return None

        error_text = response.text[:200] if response.text else "No error message"
        print(f"\nWarning: API request failed (status code: {response.status_code})")
        print(f"Error details: {error_text}")
        if 400 <= response.status_code < 500:
            error_msg = f"API request failed (status code: {response.status_code}): {error_text}"
            set_api_error(error_msg)
        return None
    except Exception:
        if retry_count < 2:
            time.sleep(1)
            return search_tweets_by_doi(doi, cursor, retry_count + 1)
        return None


def search_all_tweets_by_doi(doi, max_total=None):
    all_tweets = []
    cursor = ""

    while True:
        result = search_tweets_by_doi(doi, cursor=cursor)
        if not result:
            break

        tweets = result.get("tweets", [])
        if tweets:
            all_tweets.extend(tweets)

        has_next_page = result.get("has_next_page", False)
        next_cursor = result.get("next_cursor")
        if not has_next_page or not next_cursor:
            break

        cursor = next_cursor
        if max_total and len(all_tweets) >= max_total:
            all_tweets = all_tweets[:max_total]
            break

    return all_tweets


def build_tweet_record(tweet, xdoi):
    collected_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    tweet_id = str(tweet.get("id", ""))
    created_at = tweet.get("createdAt", "")
    text = tweet.get("text", "") or tweet.get("fullText", "") or tweet.get("content", "")
    tweet_url = tweet.get("url", "")

    reply_count = int(tweet.get("replyCount", 0) or 0)
    retweet_count = int(tweet.get("retweetCount", 0) or 0)
    like_count = int(tweet.get("likeCount", 0) or 0)
    view_count = int(tweet.get("viewCount", 0) or 0)

    author = tweet.get("author", {})
    if not isinstance(author, dict):
        author = {}

    author_username = author.get("userName", "")
    author_name = author.get("name", "")
    author_id = str(author.get("id", ""))

    if tweet_url:
        tweet_link = tweet_url
    elif author_username and tweet_id:
        tweet_link = f"https://twitter.com/{author_username}/status/{tweet_id}"
    elif tweet_id:
        tweet_link = f"https://twitter.com/i/web/status/{tweet_id}"
    else:
        tweet_link = ""

    hashtags = []
    entities = tweet.get("entities", {})
    if isinstance(entities, dict):
        hashtags_entities = entities.get("hashtags", [])
        for tag in hashtags_entities:
            if isinstance(tag, dict):
                tag_text = tag.get("text", "")
                if tag_text:
                    hashtags.append(tag_text)

    affiliates_highlighted_label = author.get("affiliatesHighlightedLabel", {})

    return {
        "collected_time": collected_time,
        "published_time": created_at,
        "reply_count": reply_count,
        "retweet_count": retweet_count,
        "like_count": like_count,
        "view_count": view_count,
        "author": author_username or author_name or author_id or "unknown",
        "link": tweet_link,
        "tweet_id": tweet_id,
        "tweet_content": text,
        "hashtags": hashtags,
        "affiliatesHighlightedLabel": affiliates_highlighted_label,
        "Xdoi": xdoi,
    }


def load_json_file(file_path, default_value):
    if os.path.exists(file_path):
        try:
            with open(file_path, "r", encoding="utf-8") as file:
                return json.load(file)
        except Exception:
            return default_value
    return default_value


def load_progress_state():
    return load_json_file(PROGRESS_FILE, {"processed_dois": [], "last_index": 0})


def save_progress_state(processed_dois, last_index):
    progress = {
        "processed_dois": processed_dois,
        "last_index": last_index,
        "last_update": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    with open(PROGRESS_FILE, "w", encoding="utf-8") as file:
        json.dump(progress, file, ensure_ascii=False, indent=2)


def load_existing_results():
    return load_json_file(OUTPUT_JSON, [])


def save_results_file(results):
    if os.path.exists(OUTPUT_JSON):
        backup_file = OUTPUT_JSON + ".backup"
        try:
            current_size = os.path.getsize(OUTPUT_JSON)
            if not os.path.exists(backup_file) or os.path.getsize(backup_file) < current_size:
                shutil.copy2(OUTPUT_JSON, backup_file)
        except Exception:
            pass
    with open(OUTPUT_JSON, "w", encoding="utf-8") as file:
        json.dump(results, file, ensure_ascii=False, indent=2)


def save_batch_output(batch_data, batch_number):
    if not batch_data:
        return
    base_name = os.path.splitext(OUTPUT_JSON)[0]
    batch_file = f"{base_name}_part_{batch_number}.json"
    try:
        with open(batch_file, "w", encoding="utf-8") as file:
            json.dump(batch_data, file, ensure_ascii=False, indent=2)
        print(f"\nSaved batch {batch_number} ({len(batch_data)} tweets)")
    except Exception as error:
        print(f"Warning: failed to save batch {batch_number}: {error}")


def verify_tweet_contains_doi(tweet, xdoi):
    doi_suffix = xdoi.replace("doi.org/", "") if "doi.org/" in xdoi else xdoi
    text = tweet.get("text", "") or tweet.get("fullText", "") or tweet.get("content", "")
    if xdoi in text or doi_suffix in text:
        return True

    entities = tweet.get("entities", {})
    if isinstance(entities, dict):
        urls = entities.get("urls", [])
        for url_obj in urls:
            if isinstance(url_obj, dict):
                expanded_url = url_obj.get("expanded_url", "") or url_obj.get("expandedUrl", "")
                display_url = url_obj.get("display_url", "") or url_obj.get("displayUrl", "")
                if (
                    xdoi in expanded_url
                    or xdoi in display_url
                    or f"https://{xdoi}" in expanded_url
                    or f"http://{xdoi}" in expanded_url
                    or doi_suffix in expanded_url
                    or doi_suffix in display_url
                ):
                    return True
    return False


def process_single_doi(item_data):
    api_error, _ = get_api_error()
    if api_error:
        return None

    index, item = item_data
    xdoi = item.get("Xdoi", "").strip()
    if not xdoi:
        return index, xdoi, []

    tweets = search_all_tweets_by_doi(xdoi, max_total=100)
    api_error, _ = get_api_error()
    if api_error:
        return None

    if tweets:
        tweet_records = []
        for tweet in tweets:
            if verify_tweet_contains_doi(tweet, xdoi):
                tweet_records.append(build_tweet_record(tweet, xdoi))
        return index, xdoi, tweet_records
    return index, xdoi, []


def get_items_to_process(input_data, processed_dois, last_index):
    total_count = len(input_data)
    items_to_process = []
    for index in range(last_index, total_count):
        item = input_data[index]
        xdoi = item.get("Xdoi", "").strip()
        if xdoi and xdoi not in processed_dois:
            items_to_process.append((index, item))
    return items_to_process


def print_startup_summary(input_data, processed_dois, results, last_index):
    print("Starting DOI tweet search")
    print(f"Input records: {len(input_data)}")
    print(f"Processed DOI count: {len(processed_dois)}")
    print(f"Existing tweet records: {len(results)}")
    print(f"Start index: {last_index}")
    print(f"Concurrency: {MAX_WORKERS} workers, QPS limit: {QPS_LIMIT}")
    print(f"Batch size: {BATCH_SIZE}")


def handle_api_error_and_exit(processed_dois, processed_count, results):
    _, error_message = get_api_error()
    print("\nAPI error detected, processing stopped")
    print(f"Reason: {error_message}")
    save_progress_state(list(processed_dois), processed_count)
    save_results_file(results)
    print("Progress saved")


def process_all_dois(input_data, processed_dois, results, items_to_process):
    new_results_count = 0
    processed_count = 0
    results_lock = Lock()
    saved_batch_count = len(results) // BATCH_SIZE

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_item = {
            executor.submit(process_single_doi, item_data): item_data for item_data in items_to_process
        }

        with tqdm(total=len(items_to_process), desc="Processing DOI tasks") as progress_bar:
            for future in as_completed(future_to_item):
                try:
                    result = future.result()
                    if result is None:
                        api_error, _ = get_api_error()
                        if api_error:
                            handle_api_error_and_exit(processed_dois, processed_count, results)
                            return processed_count, new_results_count, saved_batch_count, True
                        progress_bar.update(1)
                        continue

                    index, xdoi, tweet_records = result
                    api_error, _ = get_api_error()
                    if api_error:
                        handle_api_error_and_exit(processed_dois, processed_count, results)
                        return processed_count, new_results_count, saved_batch_count, True

                    with results_lock:
                        if tweet_records:
                            results.extend(tweet_records)
                            new_results_count += len(tweet_records)
                            current_total = len(results)
                            current_batch_count = current_total // BATCH_SIZE
                            if current_batch_count > saved_batch_count:
                                batch_start = saved_batch_count * BATCH_SIZE
                                batch_end = current_batch_count * BATCH_SIZE
                                batch_data = results[batch_start:batch_end]
                                save_batch_output(batch_data, current_batch_count)
                                saved_batch_count = current_batch_count

                        processed_dois.add(xdoi)
                        processed_count += 1

                        if processed_count % 50 == 0:
                            save_progress_state(list(processed_dois), index + 1)
                            save_results_file(results)
                            progress_bar.set_postfix(
                                {
                                    "processed": processed_count,
                                    "new_tweets": new_results_count,
                                    "total_tweets": len(results),
                                    "batches": saved_batch_count,
                                }
                            )

                    progress_bar.update(1)
                except Exception as error:
                    error_text = str(error).lower()
                    if "401" in error_text or "403" in error_text or "unauthorized" in error_text:
                        set_api_error(f"API error detected during processing: {error}")
                    progress_bar.update(1)

    return processed_count, new_results_count, saved_batch_count, False


def save_remaining_batches(results, saved_batch_count):
    current_total = len(results)
    current_batch_count = current_total // BATCH_SIZE

    if current_batch_count > saved_batch_count:
        batch_start = saved_batch_count * BATCH_SIZE
        batch_end = current_batch_count * BATCH_SIZE
        batch_data = results[batch_start:batch_end]
        if batch_data:
            save_batch_output(batch_data, current_batch_count)
            saved_batch_count = current_batch_count

    remaining_start = saved_batch_count * BATCH_SIZE
    if remaining_start < current_total:
        remaining_data = results[remaining_start:]
        if remaining_data:
            save_batch_output(remaining_data, saved_batch_count + 1)

    return saved_batch_count + (1 if len(results) % BATCH_SIZE > 0 else 0)


def main():
    global INPUT_JSON, OUTPUT_JSON, PROGRESS_FILE
    ap = argparse.ArgumentParser(description="Search X/Twitter for tweets citing paper DOIs (twitterapi.io).")
    ap.add_argument("--input", default=INPUT_JSON,
                    help="输入 JSON: 含 Xdoi 字段的论文列表 (默认 ./works_ai_with_doi.json)")
    ap.add_argument("--outdir", default=SCRIPT_DIR, help="输出目录 (默认: 脚本所在目录)")
    args = ap.parse_args()
    INPUT_JSON = args.input
    OUTPUT_JSON = os.path.join(args.outdir, "tweets_by_doi.json")
    PROGRESS_FILE = os.path.join(args.outdir, "doi_search_progress.json")

    api_key = get_api_key()
    if not api_key:
        print(
            f"Missing API key. Set environment variable {API_KEY_ENV_NAME} before running this script."
        )
        return

    init_rate_limiter()
    input_data = load_json_file(INPUT_JSON, [])
    if not input_data:
        print("No input records found")
        return

    progress = load_progress_state()
    processed_dois = set(progress.get("processed_dois", []))
    last_index = progress.get("last_index", 0)
    results = load_existing_results()

    print_startup_summary(input_data, processed_dois, results, last_index)
    items_to_process = get_items_to_process(input_data, processed_dois, last_index)
    if not items_to_process:
        print("No DOI records to process")
        return

    print(f"Pending DOI records: {len(items_to_process)}")
    _, _, saved_batch_count, stopped_by_api_error = process_all_dois(
        input_data, processed_dois, results, items_to_process
    )
    if stopped_by_api_error:
        return

    save_progress_state(list(processed_dois), len(input_data))
    save_results_file(results)
    total_batches = save_remaining_batches(results, saved_batch_count)

    print("\nCompleted")
    print(f"Processed DOI records: {len(processed_dois)}")
    print(f"Collected tweets: {len(results)}")
    print(f"Saved batch files: {total_batches}")


if __name__ == "__main__":
    main()
