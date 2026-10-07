import os
import re
import time
import json
import logging
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

AI_KEYWORDS = {
    "Core AI terms": ["artificial intelligence", "artificial-intelligence", "AI"],
    "Learning paradigms": ["machine learning", "deep learning", "reinforcement learning",
                           "supervised learning", "unsupervised learning",
                           "self-supervised learning", "transfer learning"],
    "Model architectures": ["neural network", "artificial neural network", "attention mechanism",
                            "self-attention", "convolutional neural network",
                            "recurrent neural network", "generative adversarial network",
                            "diffusion model", "graph neural network", "autoencoder"],
    "Generative AI and large language models": [
        "large language model", "LLM", "generative AI", "generative artificial intelligence",
        "vision-language model", "artificial general intelligence", "prompt engineering",
        "retrieval-augmented generation", "conversational AI", "chatbot", "AI agent",
        "agentic AI"],
    "Landmark AI systems": ["GPT", "ChatGPT", "DALL-E", "Stable Diffusion", "Midjourney",
                            "AlphaFold", "AlphaGo", "AlphaZero"],
    "AI organizations": ["OpenAI", "Google DeepMind", "Anthropic", "Meta AI", "Hugging Face",
                         "Mistral AI", "Stability AI", "xAI", "NVIDIA"],
}
search_keywords = [word for group in AI_KEYWORDS.values() for word in group]
KEYWORD_PATTERN = re.compile(
    r"\b(?:" + "|".join(re.escape(w) for w in sorted(set(search_keywords), key=len, reverse=True)) + r")\b",
    re.IGNORECASE,
)


def matches_ai(*texts):
    return any(KEYWORD_PATTERN.search(t) for t in texts if t)


logging.basicConfig(level=logging.INFO)

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")
CHECKPOINT_FILE = os.path.join(OUTPUT_DIR, "checkpoint.json")
os.makedirs(OUTPUT_DIR, exist_ok=True)


def create_browser():
    options = Options()
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("user-agent=Mozilla/5.0 Chrome/122 Safari/537.36")
    options.add_experimental_option("detach", True)
    return webdriver.Chrome(options=options)

def load_checkpoint():
    if os.path.exists(CHECKPOINT_FILE):
        try:
            with open(CHECKPOINT_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logging.warning(f"failed to load checkpoint: {e}")
    return {
        "processed_urls": set(),
        "keyword_progress": {}
    }

def save_checkpoint(processed_urls, keyword_progress):
    data = {
        "processed_urls": list(processed_urls),
        "keyword_progress": keyword_progress
    }
    with open(CHECKPOINT_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def save_article(keyword, article_data):
    safe = re.sub(r"[^0-9A-Za-z]+", "_", keyword).strip("_") or "news"
    filename = f"{safe}_news.json"
    filepath = os.path.join(OUTPUT_DIR, filename)

    existing_data = []
    if os.path.exists(filepath):
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                existing_data = json.load(f)
        except Exception:
            pass

    existing_data.append(article_data)

    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(existing_data, f, ensure_ascii=False, indent=2)

    logging.info(f"saved article to {filepath}")

def process_keyword(driver, keyword, checkpoint):
    processed_urls = set(checkpoint.get("processed_urls", []))
    keyword_progress = checkpoint.get("keyword_progress", {})

    page_num = keyword_progress.get(keyword, {}).get("page", 1)

    while True:
        page_url = f"https://www.bbc.com/search?q={keyword}&page={page_num}"
        logging.info(f"[{keyword}] page {page_num}: {page_url}")
        driver.get(page_url)
        time.sleep(2)

        try:
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.XPATH, "//*[@id='main-content']"))
            )
        except Exception:
            logging.info(f"[{keyword}] main content failed to load, stopping")
            break

        articles = driver.find_elements(By.XPATH, "//*[@id='main-content']/div[1]/div/div[2]/div/div")
        if not articles:
            logging.info(f"[{keyword}] no articles on this page, stopping")
            break

        for i, article in enumerate(articles, start=1):
            try:
                link_element = article.find_element(By.XPATH, ".//div/a")
                news_url = link_element.get_attribute("href")
                if news_url:
                    if news_url in processed_urls:
                        logging.info(f"[{keyword}] already processed: {news_url}")
                        continue

                    logging.info(f"[{keyword}] article link: {news_url}")
                    driver.execute_script("window.open(arguments[0]);", news_url)
                    driver.switch_to.window(driver.window_handles[-1])

                    try:
                        title_elem = WebDriverWait(driver, 5).until(
                            EC.presence_of_element_located((By.XPATH, "//h1[contains(@class,'sc-f98b1ad2-0')]"))
                        )
                        news_title = title_elem.text.strip()
                    except Exception:
                        news_title = "title not found"

                    try:
                        paragraphs = driver.find_elements(By.XPATH, "//article//p")
                        content_text = " ".join([p.text.strip() for p in paragraphs if p.text.strip()])
                    except Exception:
                        content_text = ""

                    try:
                        publish_date = driver.find_element(By.XPATH, "//time").get_attribute("datetime")
                    except Exception:
                        publish_date = datetime.now().isoformat()

                    article_data = {
                        "title": news_title,
                        "url": news_url,
                        "content": content_text,
                        "keyword": keyword,
                        "publish_date": publish_date,
                        "crawl_date": datetime.now().isoformat()
                    }

                    if matches_ai(news_title, content_text):
                        logging.info(f"[{keyword}] keyword matched: {news_title}")
                        article_data["is_relevant"] = True
                        save_article(keyword, article_data)
                    else:
                        logging.info(f"[{keyword}] no keyword match, skipped")
                        article_data["is_relevant"] = False

                    processed_urls.add(news_url)

                    if len(processed_urls) % 5 == 0:
                        keyword_progress[keyword] = {"page": page_num}
                        save_checkpoint(processed_urls, keyword_progress)

                    driver.close()
                    driver.switch_to.window(driver.window_handles[0])
                    time.sleep(1)

            except Exception as e:
                logging.warning(f"[{keyword}] skipped article {i}: {e}")
                continue

        keyword_progress[keyword] = {"page": page_num}
        save_checkpoint(processed_urls, keyword_progress)

        try:
            next_button = driver.find_element(By.XPATH, "//button[@data-testid='pagination-next-button' and @aria-label='Next Page']")
            if next_button.is_enabled():
                page_num += 1
                time.sleep(2)
            else:
                logging.info(f"[{keyword}] reached last page")
                break
        except Exception:
            logging.info(f"[{keyword}] no next-page button, done paging")
            break

def main():
    checkpoint = load_checkpoint()
    processed_urls = set(checkpoint.get("processed_urls", []))
    keyword_progress = checkpoint.get("keyword_progress", {})

    driver = create_browser()
    driver.implicitly_wait(10)

    try:
        for keyword in search_keywords:
            logging.info(f"processing keyword: {keyword}")
            process_keyword(driver, keyword, checkpoint)
            logging.info(f"finished keyword: {keyword}\n{'-'*60}")
    except KeyboardInterrupt:
        logging.info("interrupted by user, saving checkpoint...")
    except Exception as e:
        logging.error(f"error: {e}")
    finally:
        save_checkpoint(processed_urls, keyword_progress)
        driver.quit()
        logging.info("all keywords done")

if __name__ == "__main__":
    main()
