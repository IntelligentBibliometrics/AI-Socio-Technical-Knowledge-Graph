
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from datetime import datetime
import json
import os
from tqdm import tqdm

chrome_options = Options()
chrome_options.add_argument('--no-sandbox')
chrome_options.add_argument('--disable-dev-shm-usage')

driver = webdriver.Chrome(options=chrome_options)

progress_file = "../data/mit/progress.json"
start_page = 1

if os.path.exists(progress_file):
    try:
        with open(progress_file, 'r', encoding='utf-8') as f:
            progress_data = json.load(f)
            start_page = progress_data.get('last_page', 1) + 1
            print(f"checkpoint found, resuming from page {start_page}...")
    except Exception as e:
        print(f"failed to read progress file: {e}; starting over")

scrape_start_time = datetime.now()
print(f"start time: {scrape_start_time.strftime('%Y-%m-%d %H:%M:%S')}")

titles = []
abstracts = []
publish_dates = []
urls = []
scrape_times = []

total_pages = 85
pbar = tqdm(range(start_page, total_pages + 1), desc="Scraping", unit="page")

for page in pbar:
    pbar.set_description(f"scraping page {page}")
    
    url = f"https://news.mit.edu/topic/artificial-intelligence2?type=1&page={page-1}"
    driver.get(url)
    
    wait = WebDriverWait(driver, 10)
    try:
        wait.until(EC.presence_of_element_located((By.ID, "block-mit-content")))
    except Exception as e:
        pbar.write(f"page {page} failed to load: {e}")
        continue
    
    page_articles = 0
    for i in range(1, 16):
        try:
            article_scrape_time = datetime.now()
            
            title_xpath = f"//*[@id='block-mit-content']/div/div/div/div[2]/div[{i}]/article/div[2]/h3/a/span"
            title_element = driver.find_element(By.XPATH, title_xpath)
            title = title_element.text.strip()
            titles.append(title)
            
            url_xpath = f"//*[@id='block-mit-content']/div/div/div/div[2]/div[{i}]/article/div[2]/h3/a"
            url_element = driver.find_element(By.XPATH, url_xpath)
            url = url_element.get_attribute('href')
            urls.append(url)
            
            abstract = "No abstract"
            abstract_selectors = [
                f"//*[@id='block-mit-content']/div/div/div/div[2]/div[{i}]/article/div[2]/p[1]/span",
                f"//*[@id='block-mit-content']/div/div/div/div[2]/div[{i}]/article/div[2]/p[1]",
                f"//*[@id='block-mit-content']/div/div/div/div[2]/div[{i}]/article/div[2]/div[1]",
                f"//*[@id='block-mit-content']/div/div/div/div[2]/div[{i}]/article/div[2]//p[1]"
            ]
            
            for selector in abstract_selectors:
                try:
                    abstract_element = driver.find_element(By.XPATH, selector)
                    abstract = abstract_element.text.strip()
                    if abstract and len(abstract) > 5:
                        break
                except:
                    continue
            
            abstracts.append(abstract)
            
            publish_date = "Unknown date"
            date_selectors = [
                f"//*[@id='block-mit-content']/div/div/div/div[2]/div[{i}]/article/div[2]/p[2]/time",
                f"//*[@id='block-mit-content']/div/div/div/div[2]/div[{i}]/article/div[2]//time",
                f"//*[@id='block-mit-content']/div/div/div/div[2]/div[{i}]/article/div[2]/p[2]",
                f"//*[@id='block-mit-content']/div/div/div/div[2]/div[{i}]/article/div[2]//p[2]"
            ]
            
            for selector in date_selectors:
                try:
                    date_element = driver.find_element(By.XPATH, selector)
                    publish_date = date_element.text.strip()
                    if publish_date and len(publish_date) > 3:
                        break
                except:
                    continue
            
            publish_dates.append(publish_date)
            
            scrape_time_str = article_scrape_time.strftime('%Y-%m-%d %H:%M:%S')
            scrape_times.append(scrape_time_str)
            
            page_articles += 1
            
        except Exception as e:
            pbar.write(f"  article {i} failed: {e}")
            titles.append(f"Failed article {i}")
            urls.append("")
            abstracts.append("Failed")
            publish_dates.append("Unknown date")
            scrape_times.append(datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
            page_articles += 1
    
    pbar.set_postfix({"page_articles": page_articles, "total": len(titles)})
    
    if page_articles > 0:
        page_data = []
        start_idx = max(0, len(titles) - page_articles)
        for i in range(page_articles):
            idx = start_idx + i
            if idx < len(titles):
                article = {
                    "title": titles[idx],
                    "url": urls[idx],
                    "abstract": abstracts[idx],
                    "publish_date": publish_dates[idx],
                    "scrape_time": scrape_times[idx],
                    "page_number": page
                }
                page_data.append(article)
        
        page_filename = f"mit_news_page_{page:03d}.json"
        page_filepath = os.path.join("../data/mit", page_filename)
        
        with open(page_filepath, 'w', encoding='utf-8') as f:
            json.dump(page_data, f, ensure_ascii=False, indent=2)
        
        pbar.write(f"page {page} saved: {page_filename}")
    
    progress_data = {
        'last_page': page,
        'total_articles': len(titles),
        'last_update': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    }
    with open(progress_file, 'w', encoding='utf-8') as f:
        json.dump(progress_data, f, ensure_ascii=False, indent=2)
    
    import time
    time.sleep(2)

pbar.close()

scrape_end_time = datetime.now()
print(f"\nend time: {scrape_end_time.strftime('%Y-%m-%d %H:%M:%S')}")
print(f"total time: {(scrape_end_time - scrape_start_time).total_seconds():.2f}s")
print(f"collected {len(titles)} articles")

output_dir = "../data/mit"
os.makedirs(output_dir, exist_ok=True)

articles_data = []
for i in range(len(titles)):
    article = {
        "title": titles[i],
        "url": urls[i],
        "abstract": abstracts[i],
        "publish_date": publish_dates[i],
        "scrape_time": scrape_times[i]
    }
    articles_data.append(article)

json_filename = "mit_news.json"
json_filepath = os.path.join(output_dir, json_filename)

with open(json_filepath, 'w', encoding='utf-8') as f:
    json.dump(articles_data, f, ensure_ascii=False, indent=2)

print(f"\ndata saved to: {json_filepath}")

print("generating aggregated JSON file...")
aggregated_data = {
    "scrape_info": {
        "start_time": scrape_start_time.strftime('%Y-%m-%d %H:%M:%S'),
        "end_time": scrape_end_time.strftime('%Y-%m-%d %H:%M:%S'),
        "total_duration_seconds": (scrape_end_time - scrape_start_time).total_seconds(),
        "total_pages": 85,
        "total_articles": len(articles_data)
    },
    "articles": articles_data
}

aggregated_filename = "mit_news_aggregated.json"
aggregated_filepath = os.path.join(output_dir, aggregated_filename)

with open(aggregated_filepath, 'w', encoding='utf-8') as f:
    json.dump(aggregated_data, f, ensure_ascii=False, indent=2)

print(f"aggregated data saved to: {aggregated_filepath}")
print(f"aggregated file has {len(articles_data)} articles across 85 pages")

import time
print("browser will stay open for 5 seconds...")
time.sleep(5)

driver.quit()
