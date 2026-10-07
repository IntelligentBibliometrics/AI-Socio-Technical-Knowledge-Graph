from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import pandas as pd
import time
import json
import os
import random
import logging

class IEEESpectrumCrawler:
    def __init__(self):
        self.url = "https://spectrum.ieee.org/artificial-intelligence"
        self.output_dir = os.path.join(os.path.dirname(__file__), 'output')
        self.checkpoint_file = os.path.join(self.output_dir, 'ieee_checkpoint.json')
        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir)
        self.setup_logging()
        self.setup_driver()
        self.articles = self.load_checkpoint()
        
    def setup_logging(self):
        log_file = os.path.join(self.output_dir, 'crawler.log')
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(log_file, encoding='utf-8'),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger(__name__)
        
    def setup_driver(self):
        chrome_options = Options()
        chrome_options.add_argument("--headless=new")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--remote-debugging-port=9222")
        self.driver = webdriver.Chrome(options=chrome_options)
        
    def load_checkpoint(self):
        if os.path.exists(self.checkpoint_file):
            try:
                with open(self.checkpoint_file, 'r', encoding='utf-8') as f:
                    articles = json.load(f)
                self.logger.info(f"loaded checkpoint with {len(articles)} articles")
                return articles
            except Exception as e:
                self.logger.warning(f"failed to load checkpoint: {e}")
        return []

    def save_checkpoint(self):
        try:
            with open(self.checkpoint_file, 'w', encoding='utf-8') as f:
                json.dump(self.articles, f, ensure_ascii=False, indent=2)
            self.logger.info(f"checkpoint saved, {len(self.articles)} articles total")
            latest_json = os.path.join(self.output_dir, 'ieee_spectrum_articles_latest.json')
            with open(latest_json, 'w', encoding='utf-8') as f:
                json.dump(self.articles, f, ensure_ascii=False, indent=2)
            self.logger.info(f"exported latest JSON to {latest_json}")
        except Exception as e:
            self.logger.warning(f"failed to save checkpoint: {e}")

    def get_articles(self):
        try:
            self.driver.get(self.url)
            articles = self.articles.copy()
            start_time = time.time()
            
            self.logger.info("waiting for initial page load...")
            WebDriverWait(self.driver, 15).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "article"))
            )
            
            last_count = 0
            no_new_articles_count = 0
            scroll_count = 0
            
            for _ in range(40):
                if scroll_count > 0 and scroll_count % 5 == 0:
                    pause_time = 10 + random.randint(0, 10)
                    self.logger.info(f"scrolled {scroll_count} times, pausing {pause_time}s...")
                    time.sleep(pause_time)
                
                self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(3)
                
                current_articles = self.driver.find_elements(By.CSS_SELECTOR, "article")
                current_count = len(current_articles)
                
                elapsed_time = time.time() - start_time
                articles_per_minute = (current_count / elapsed_time) * 60
                
                if current_count == last_count:
                    no_new_articles_count += 1
                    if no_new_articles_count >= 3:
                        self.logger.info(f"reached bottom, {current_count} articles loaded")
                        self.logger.info(f"average speed: {articles_per_minute:.2f} articles/min")
                        break
                else:
                    no_new_articles_count = 0
                    self.logger.info(f"loaded {current_count} articles (speed: {articles_per_minute:.2f}/min)")
                
                last_count = current_count
                scroll_count += 1
                
                time.sleep(random.uniform(1, 3))
            
            article_elements = self.driver.find_elements(By.CSS_SELECTOR, "article")
            self.logger.info(f"processing {len(article_elements)} articles...")
            
            existing_links = set(a["link"] for a in articles)

            for index, article in enumerate(article_elements, 1):
                try:
                    try:
                        title = article.find_element(By.CSS_SELECTOR, "h2").text
                    except:
                        title = ""
                    try:
                        link = article.find_element(By.CSS_SELECTOR, "a").get_attribute("href")
                    except:
                        link = ""
                    try:
                        date = article.find_element(By.CSS_SELECTOR, "time").text
                    except:
                        date = ""
                    try:
                        summary = article.find_element(By.CSS_SELECTOR, "p").text
                    except:
                        summary = ""
                    if title and link and link not in existing_links:
                        news_item = {
                            "title": title,
                            "link": link,
                            "date": date,
                            "summary": summary
                        }
                        articles.append(news_item)
                        existing_links.add(link)
                        self.articles = articles
                        self.save_checkpoint()
                        self.logger.info(f"saved article: {title}")
                    if index % 10 == 0:
                        self.logger.info(f"processed {index}/{len(article_elements)} articles")
                except Exception as e:
                    self.logger.error(f"error on article {index}: {str(e)}")
                    continue
                    
            total_time = time.time() - start_time
            self.logger.info(f"done, {len(articles)} articles in {total_time/60:.2f} min")
            return articles
            
        except Exception as e:
            self.logger.error(f"error while scraping: {str(e)}")
            return []
            
    def save_to_csv(self, articles):
        if not articles:
            self.logger.warning("no articles to save")
            return
        df = pd.DataFrame(articles)
        filename = os.path.join(self.output_dir, "ieee_spectrum_articles.csv")
        df.to_csv(filename, index=False, encoding='utf-8-sig')
        self.logger.info(f"articles saved to {filename}")
        
    def save_to_json(self, articles):
        if not articles:
            self.logger.warning("no articles to save")
            return
        filename = os.path.join(self.output_dir, "ieee_spectrum_articles.json")
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(articles, f, ensure_ascii=False, indent=4)
        self.logger.info(f"articles saved to {filename}")
        
    def close(self):
        self.driver.quit()
        self.logger.info("browser closed")

def main():
    crawler = IEEESpectrumCrawler()
    try:
        crawler.logger.info("scraping IEEE Spectrum AI news...")
        articles = crawler.get_articles()
        crawler.save_to_csv(articles)
        crawler.save_to_json(articles)
    except Exception as e:
        crawler.logger.error(f"crawler error: {str(e)}")
    finally:
        crawler.close()

if __name__ == "__main__":
    main()
