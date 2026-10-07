import re
import time
import json
import os
import logging
from datetime import datetime

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

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


OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "outputs")
CHECKPOINT_FILE = os.path.join(OUTPUT_DIR, "cnn_checkpoint.json")
MAIN_DATA_FILE = os.path.join(OUTPUT_DIR, "cnn_all_news.json")

def create_browser():
    q1 = Options()
    q1.add_argument("--no-sandbox")
    q1.add_argument("--disable-blink-features=AutomationControlled")
    q1.add_argument("user-agent=Mozilla/5.0 Chrome/122 Safari/537.36")
    q1.add_experimental_option("detach", True)
    return webdriver.Chrome(options=q1)


def get_article_content_enhanced(driver):
    content_text = ""
    
    content_selectors = [
        "//div[contains(@class, 'article__content')]//p",
        "//div[contains(@class, 'zn-body__paragraph')]", 
        "//div[contains(@data-module, 'ArticleBody')]//p",
        "//div[contains(@class, 'pg-rail-tall__body')]//p",
        "//div[contains(@class, 'l-container')]//p",
        "//div[contains(@class, 'zn-body')]//p",
        
        "//article//p",
        "//main//p", 
        "//div[contains(@class, 'story')]//p",
        "//div[contains(@class, 'content')]//p",
        "//section[contains(@class, 'article')]//p",
        "//div[contains(@class, 'post-content')]//p",
        "//div[contains(@class, 'entry-content')]//p",
        
        "//p[string-length(text()) > 50]",
        "//div[contains(@class, 'paragraph')]",
        "//*[contains(@class, 'text-content')]//p",
        "//div[contains(@class, 'body-text')]//p",
        "//div[contains(@class, 'article-body')]//p",
        
        "//p[not(ancestor::nav) and not(ancestor::header) and not(ancestor::footer)]"
    ]
    
    successful_selector = None
    
    for i, selector in enumerate(content_selectors):
        try:
            paragraphs = driver.find_elements(By.XPATH, selector)
            if paragraphs and len(paragraphs) >= 2:
                valid_paragraphs = []
                for p in paragraphs:
                    text = p.text.strip()
                    if (text and len(text) > 20 and 
                        not any(nav_word in text.lower() for nav_word in 
                               ['subscribe', 'follow us', 'share', 'cookie', 'advertisement', 'menu'])):
                        valid_paragraphs.append(text)
                
                temp_content = " ".join(valid_paragraphs)
                
                if len(temp_content) > 200 and len(valid_paragraphs) >= 2:
                    content_text = temp_content
                    successful_selector = selector
                    logging.info(f"selector matched #{i+1}: {selector}")
                    logging.info(f"got {len(valid_paragraphs)} paragraphs, {len(content_text)} chars")
                    break
                    
        except Exception as e:
            logging.debug(f"selector #{i+1} failed: {e}")
            continue
    
    if not content_text:
        try:
            logging.warning(f"all selectors failed, trying fallback")
            
            all_paragraphs = driver.find_elements(By.TAG_NAME, "p")
            if all_paragraphs:
                filtered_content = []
                for p in all_paragraphs:
                    text = p.text.strip()
                    if (len(text) > 30 and 
                        not any(skip_word in text.lower() for skip_word in 
                               ['cookie', 'privacy', 'terms', 'subscribe', 'newsletter', 'follow', 'share'])):
                        filtered_content.append(text)
                
                if len(filtered_content) >= 3:
                    content_text = " ".join(filtered_content[:15])
                    logging.info(f"fallback succeeded, {len(filtered_content)} paragraphs")
                    
        except Exception as e:
            logging.error(f"fallback also failed: {e}")
    
    return content_text, successful_selector

def wait_for_content_load(driver, max_attempts=2):
    for attempt in range(max_attempts):
        try:
            WebDriverWait(driver, 10).until(
                lambda d: d.execute_script("return document.readyState") == "complete"
            )
            
            WebDriverWait(driver, 8).until(
                EC.presence_of_element_located((By.TAG_NAME, "p"))
            )
            
            wait_time = 3 + attempt * 2
            time.sleep(wait_time)
            
            paragraphs = driver.find_elements(By.TAG_NAME, "p")
            if len(paragraphs) >= 3:
                logging.info(f"page loaded, found {len(paragraphs)} paragraphs")
                return True
                
        except Exception as e:
            logging.warning(f"content wait failed (attempt {attempt+1}): {e}")
            if attempt < max_attempts - 1:
                time.sleep(2)
    
    logging.warning(f"page may be incompletely loaded")
    return False

def find_news_elements_flexible(driver):
    news_elements = []
    
    search_selectors = [
        "//div[contains(@class, 'cnn-search__result')]",
        "//div[contains(@class, 'search-result')]", 
        "//div[contains(@class, 'search')]//a[contains(@href, '/2024/') or contains(@href, '/2025/')]",
        "//a[contains(@href, '/2024/') or contains(@href, '/2025/')]"
    ]
    
    for selector in search_selectors:
        try:
            elements = driver.find_elements(By.XPATH, selector)
            if elements:
                logging.info(f"found {len(elements)} elements with selector: {selector}")
                
                for elem in elements:
                    try:
                        if elem.tag_name == 'a':
                            link = elem.get_attribute('href')
                            title = elem.text.strip()
                        else:
                            link_elem = elem.find_element(By.TAG_NAME, 'a')
                            link = link_elem.get_attribute('href')
                            title = link_elem.text.strip()
                        
                        if (link and title and 
                            'cnn.com' in link and 
                            ('/2024/' in link or '/2025/' in link) and
                            len(title) > 10):
                            
                            news_elements.append({
                                'url': link,
                                'title': title,
                                'element': elem
                            })
                            
                    except Exception as e:
                        logging.debug(f"failed to process element: {e}")
                        continue
                
                if news_elements:
                    break
                    
        except Exception as e:
            logging.debug(f"selector failed: {e}")
            continue
    
    seen_urls = set()
    unique_news = []
    for news in news_elements:
        if news['url'] not in seen_urls:
            seen_urls.add(news['url'])
            unique_news.append(news)
    
    logging.info(f"found {len(unique_news)} unique articles")
    return unique_news

def load_checkpoint():
    if os.path.exists(CHECKPOINT_FILE):
        try:
            with open(CHECKPOINT_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                data["processed_urls"] = set(data.get("processed_urls", []))
                return data
        except Exception as e:
            logging.warning(f"failed to load checkpoint: {e}")
    return {
        "processed_urls": set(),
        "current_page": 1,
        "total_collected": 0,
        "content_success_rate": 0
    }

def save_checkpoint(processed_urls, current_page, total_collected, content_success_rate=0):
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    data = {
        "processed_urls": list(processed_urls),
        "current_page": current_page,
        "total_collected": total_collected,
        "content_success_rate": content_success_rate,
        "last_update": datetime.now().isoformat()
    }
    with open(CHECKPOINT_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    logging.info(f"checkpoint saved: page {current_page}, {total_collected} collected, content rate {content_success_rate:.1f}%")

def load_main_data():
    if os.path.exists(MAIN_DATA_FILE):
        try:
            with open(MAIN_DATA_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return data.get("news_list", [])
        except Exception as e:
            logging.warning(f"failed to load main data file: {e}")
    return []

def save_main_data_realtime(all_news_data):
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    relevant_news = [news for news in all_news_data if news.get("is_relevant", False)]
    content_success_count = len([news for news in all_news_data if news.get("content") and len(news.get("content", "")) > 100])
    
    keyword_stats = {}
    for keyword in search_keywords:
        keyword_news = [news for news in all_news_data if news.get("search_keyword") == keyword]
        keyword_relevant = [news for news in keyword_news if news.get("is_relevant", False)]
        keyword_stats[keyword] = {
            "total_count": len(keyword_news),
            "relevant_count": len(keyword_relevant),
            "content_success_count": len([news for news in keyword_news if news.get("content") and len(news.get("content", "")) > 100])
        }
    
    json_data_all = {
        "version": "ENHANCED_FIXED_WITH_FLEXIBLE_SELECTORS_MULTI_KEYWORDS",
        "search_keywords": search_keywords,
        "collection_time": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        "total_count": len(all_news_data),
        "relevant_count": len(relevant_news),
        "content_success_count": content_success_count,
        "content_success_rate": f"{(content_success_count/len(all_news_data)*100):.1f}%" if all_news_data else "0%",
        "keyword_statistics": keyword_stats,
        "news_list": all_news_data
    }
    
    with open(MAIN_DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(json_data_all, f, ensure_ascii=False, indent=2)
    
    if relevant_news:
        json_data_relevant = {
            "version": "ENHANCED_FIXED_WITH_FLEXIBLE_SELECTORS_MULTI_KEYWORDS",
            "search_keywords": search_keywords,
            "collection_time": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            "relevant_count": len(relevant_news),
            "keyword_statistics": {k: v for k, v in keyword_stats.items() if v["relevant_count"] > 0},
            "news_list": relevant_news
        }
        
        relevant_file = os.path.join(OUTPUT_DIR, "cnn_relevant_news.json")
        with open(relevant_file, 'w', encoding='utf-8') as f:
            json.dump(json_data_relevant, f, ensure_ascii=False, indent=2)
    
    logging.info(f"saved: {len(all_news_data)} articles, {len(relevant_news)} relevant")
    return MAIN_DATA_FILE

def get_page_url(search_keyword, page_num):
    from_param = (page_num - 1) * 10
    return f"https://edition.cnn.com/search?q={search_keyword}&from={from_param}&size=10&page={page_num}&sort=newest&types=all&section="

def process_single_page_enhanced_fixed(driver, page_num, processed_urls, search_keyword):
    page_url = get_page_url(search_keyword, page_num)
    logging.info(f"page {page_num} (keyword: {search_keyword}): {page_url}")
    
    driver.get(page_url)
    time.sleep(3)
    
    try:
        WebDriverWait(driver, 10).until(
            lambda d: d.execute_script("return document.readyState") == "complete"
        )
        time.sleep(2)
    except:
        logging.warning(f"page {page_num} load timeout")
    
    page_news_data = []
    content_success_count = 0
    
    news_elements = find_news_elements_flexible(driver)
    
    if not news_elements:
        logging.warning(f"no article elements on page {page_num}")
        return [], False, driver
    
    logging.info(f"page {page_num}: found {len(news_elements)} articles")
    
    for news_index, news_item in enumerate(news_elements, 1):
        try:
            news_url = news_item['url']
            news_title = news_item['title']
            
            if news_url in processed_urls:
                logging.info(f"already processed: {news_url}")
                continue
            
            logging.info(f"processing article {news_index}: {news_title[:50]}...")
            
            content_text = ""
            publish_date = ""
            successful_selector = None
            
            try:
                driver.execute_script("window.open(arguments[0]);", news_url)
                driver.switch_to.window(driver.window_handles[-1])
                
                if wait_for_content_load(driver):
                    
                    content_text, successful_selector = get_article_content_enhanced(driver)
                    
                    if content_text:
                        content_success_count += 1
                        logging.info(f"content fetched, {len(content_text)} chars")
                    else:
                        logging.warning(f"content fetch failed")
                
                time_selectors = [
                    "//time",
                    "//div[contains(@class, 'timestamp')]",
                    "//span[contains(@class, 'date')]",
                    "//div[contains(@class, 'publish')]",
                    "//*[contains(@class, 'date')]"
                ]
                
                for selector in time_selectors:
                    try:
                        time_element = driver.find_element(By.XPATH, selector)
                        publish_date = time_element.get_attribute("datetime") or time_element.text.strip()
                        if publish_date:
                            break
                    except:
                        continue
                
                if not publish_date:
                    publish_date = datetime.now().isoformat()
                    
            except Exception as e:
                logging.warning(f"failed to fetch article content: {e}")
                content_text = ""
                publish_date = datetime.now().isoformat()
            finally:
                try:
                    if len(driver.window_handles) > 1:
                        driver.close()
                        driver.switch_to.window(driver.window_handles[0])
                except Exception as e:
                    logging.warning(f"failed to close window: {e}")
                    try:
                        driver.quit()
                    except:
                        pass
                    driver = create_browser()
                    driver.get(page_url)
                    time.sleep(3)
            
            news_info = {
                'title': news_title,
                'url': news_url,
                'content': content_text,
                'content_length': len(content_text),
                'successful_selector': successful_selector,
                'page': page_num,
                'index_in_page': news_index,
                'publish_date': publish_date,
                'crawl_time': datetime.now().isoformat(),
                'search_keyword': search_keyword
            }
            
            is_relevant = matches_ai(news_title, content_text)
            news_info['is_relevant'] = is_relevant
            if is_relevant:
                logging.info(f"keyword matched: {news_title}")
            else:
                logging.info(f"no keyword match: {news_title}")
            
            page_news_data.append(news_info)
            processed_urls.add(news_url)
            time.sleep(1)
                
        except Exception as e:
            logging.warning(f"page {page_num} article {news_index} failed: {e}")
            try:
                if len(driver.window_handles) > 1:
                    driver.close()
                    driver.switch_to.window(driver.window_handles[0])
            except:
                try:
                    driver.quit()
                except:
                    pass
                driver = create_browser()
                driver.get(page_url)
                time.sleep(3)
            continue
    
    page_success_rate = (content_success_count / len(page_news_data) * 100) if page_news_data else 0
    logging.info(f"page {page_num} content rate: {page_success_rate:.1f}% ({content_success_count}/{len(page_news_data)})")
    
    return page_news_data, len(page_news_data) > 0, driver

def main():
    checkpoint = load_checkpoint()
    processed_urls = checkpoint["processed_urls"]
    current_page = checkpoint["current_page"]
    total_collected = checkpoint["total_collected"]
    
    all_news_data = load_main_data()
    
    logging.info(f"starting CNN multi-keyword crawler")
    logging.info(f"keywords: {search_keywords}")
    logging.info(f"resuming from page {current_page}, {total_collected} collected")
    logging.info(f"existing data: {len(all_news_data)} articles")
    logging.info(f"using flexible selector strategy")
    
    driver = create_browser()
    total_content_success = 0
    
    try:
        for keyword_index, search_keyword in enumerate(search_keywords):
            logging.info(f"\nsearching keyword {keyword_index+1}/{len(search_keywords)}: '{search_keyword}'")
            
            for page_num in range(1, 4):
                logging.info(f"\nkeyword '{search_keyword}' page {page_num}...")
                
                page_news_data, articles_found, driver = process_single_page_enhanced_fixed(driver, page_num, processed_urls, search_keyword)
                
                if not articles_found:
                    logging.info(f"keyword '{search_keyword}' page {page_num}: no new articles")
                    break
                
                page_content_success = len([news for news in page_news_data if news.get("content") and len(news.get("content", "")) > 100])
                total_content_success += page_content_success
                
                all_news_data.extend(page_news_data)
                total_collected += len(page_news_data)
                
                overall_success_rate = (total_content_success / total_collected * 100) if total_collected > 0 else 0
                
                save_main_data_realtime(all_news_data)
                
                save_checkpoint(processed_urls, current_page, total_collected, overall_success_rate)
                
                logging.info(f"keyword '{search_keyword}' page {page_num} done, {len(page_news_data)} collected")
                logging.info(f"total {total_collected} articles, content rate: {overall_success_rate:.1f}%")
                
                time.sleep(2)
                
            logging.info(f"keyword '{search_keyword}' done")
            time.sleep(3)
    
    except KeyboardInterrupt:
        logging.info("interrupted by user, saving data...")
    except Exception as e:
        logging.error(f"error: {e}")
    finally:
        if all_news_data:
            json_file_path_all = save_main_data_realtime(all_news_data)
            relevant_count = len([news for news in all_news_data if news.get("is_relevant", False)])
            content_success_count = len([news for news in all_news_data if news.get("content") and len(news.get("content", "")) > 100])
            final_success_rate = (content_success_count / len(all_news_data) * 100) if all_news_data else 0
            
            keyword_summary = {}
            for keyword in search_keywords:
                keyword_news = [news for news in all_news_data if news.get("search_keyword") == keyword]
                keyword_relevant = [news for news in keyword_news if news.get("is_relevant", False)]
                keyword_summary[keyword] = {
                    "total": len(keyword_news),
                    "relevant": len(keyword_relevant)
                }
            
            logging.info("done: %d articles, %d relevant, content rate %.1f%% (%d/%d)",
                         len(all_news_data), relevant_count, final_success_rate,
                         content_success_count, len(all_news_data))
            logging.info("all articles saved to: %s", json_file_path_all)
            for keyword, stats in keyword_summary.items():
                logging.info("keyword '%s': %d articles, %d relevant", keyword, stats['total'], stats['relevant'])
        
        final_success_rate = (total_content_success / total_collected * 100) if total_collected > 0 else 0
        save_checkpoint(processed_urls, current_page, total_collected, final_success_rate)
        
        
        logging.info("crawler finished")

if __name__ == "__main__":
    main() 