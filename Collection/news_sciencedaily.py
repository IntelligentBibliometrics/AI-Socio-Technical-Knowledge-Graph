
import requests
from bs4 import BeautifulSoup
import json
import time
from datetime import datetime
from tqdm import tqdm
import os
import re
import argparse

class ScienceDailyScraper:
    def __init__(self, progress_file="../data/sciencedaily/progress.json"):
        self.base_url = "https://www.sciencedaily.com/news/computers_math/artificial_intelligence/"
        self.all_articles = []
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })
        self.scrape_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.progress_file = progress_file
        self.load_progress()
    
    def parse_publish_date(self, date_text):
        try:
            date_text = date_text.replace('&#151;', '').replace('—', '').strip()
            
            pattern = r'([A-Za-z]+)\.?\s+(\d+),\s+(\d{4})'
            match = re.search(pattern, date_text)
            
            if match:
                month_str, day, year = match.groups()
                month_map = {
                    'Jan': '01', 'Feb': '02', 'Mar': '03', 'Apr': '04',
                    'May': '05', 'Jun': '06', 'Jul': '07', 'Aug': '08',
                    'Sep': '09', 'Oct': '10', 'Nov': '11', 'Dec': '12'
                }
                month = month_map.get(month_str, '01')
                return f"{year}-{month}-{day.zfill(2)}"
            
            return date_text
        except Exception:
            return date_text
    
    def load_progress(self):
        try:
            if os.path.exists(self.progress_file):
                with open(self.progress_file, 'r', encoding='utf-8') as f:
                    progress_data = json.load(f)
                    self.all_articles = progress_data.get('articles', [])
                    self.last_page = progress_data.get('last_page', 0)
                    print(f"resumed: {len(self.all_articles)} articles, last page {self.last_page}")
            else:
                self.last_page = 0
        except Exception as e:
            print(f"failed to load progress file: {e}")
            self.last_page = 0
    
    def save_progress(self):
        try:
            progress_data = {
                'articles': self.all_articles,
                'last_page': self.last_page,
                'last_update': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                'total_articles': len(self.all_articles)
            }
            with open(self.progress_file, 'w', encoding='utf-8') as f:
                json.dump(progress_data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"failed to save progress file: {e}")
    
    def scrape_page(self, page_num=1):
        if page_num == 1:
            url = self.base_url
        else:
            url = f"{self.base_url}?page={page_num}"
        
        try:
            response = self.session.get(url, timeout=10)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "html.parser")
            
            articles = []
            
            all_links = soup.find_all('a', href=True)
            
            for link in all_links:
                href = link.get('href', '')
                text = link.get_text(strip=True)
                
                if '/releases/' in href and text and len(text) > 20:
                    if href.startswith('http'):
                        full_url = href
                    else:
                        full_url = "https://www.sciencedaily.com" + href
                    
                    if hasattr(self, 'scraped_urls') and full_url in self.scraped_urls:
                        continue
                    
                    parent = link.parent
                    summary = ""
                    publish_date = ""
                    
                    while parent and (not summary or not publish_date):
                        if not summary:
                            p_elem = parent.find('p')
                            if p_elem:
                                summary_text = p_elem.get_text(strip=True)
                                if (len(summary_text) > 20 and 
                                    'newsletter' not in summary_text.lower() and
                                    'rss' not in summary_text.lower()):
                                    summary = summary_text
                        
                        if not publish_date:
                            date_elem = parent.find('span', class_='story-date')
                            if date_elem:
                                publish_date = self.parse_publish_date(date_elem.get_text(strip=True))
                        
                        parent = parent.parent
                    
                    if not summary:
                        summary = text
                    
                    articles.append({
                        'title': text,
                        'url': full_url,
                        'abstract': summary,
                        'publish_date': publish_date,
                        'scrape_time': self.scrape_time,
                        'page': page_num
                    })
                    
                    if not hasattr(self, 'scraped_urls'):
                        self.scraped_urls = set()
                    self.scraped_urls.add(full_url)
            
            return articles
        except Exception as e:
            print(f"page {page_num} scrape failed: {e}")
            return []
    
    def scrape_pages(self, start_page=1, end_page=50, save_interval=5):
        if self.last_page > 0:
            start_page = self.last_page + 1
            print(f"resuming from page {start_page}")
        
        print(f"scraping ScienceDaily pages {start_page}-{end_page}")
        print(f"already have {len(self.all_articles)} articles")
        
        pbar = tqdm(range(start_page, end_page + 1), desc="Scraping", unit="page")
        no_new_articles_count = 0
        
        try:
            for page in pbar:
                articles = self.scrape_page(page)
                new_articles = []
                
                for article in articles:
                    if not any(existing['url'] == article['url'] for existing in self.all_articles):
                        new_articles.append(article)
                
                self.all_articles.extend(new_articles)
                self.last_page = page
                
                pbar.set_postfix({
                    'page': len(new_articles),
                    'total': len(self.all_articles)
                })
                
                if len(new_articles) == 0:
                    no_new_articles_count += 1
                else:
                    no_new_articles_count = 0
                
                if page % save_interval == 0:
                    self.save_progress()
                    print(f"\npage {page} done: +{len(new_articles)} articles, {len(self.all_articles)} total")
                
                if no_new_articles_count >= 3 and page > start_page + 2:
                    print(f"\n{no_new_articles_count} pages with no new articles; likely done")
                    break
                
                time.sleep(1)
                
        except KeyboardInterrupt:
            print(f"\n\ninterrupted by user, progress saved at page {self.last_page}")
            self.save_progress()
            return self.all_articles
        except Exception as e:
            print(f"\nerror while scraping: {e}")
            self.save_progress()
            return self.all_articles
        finally:
            pbar.close()
        
        self.save_progress()
        print(f"\ndone, collected {len(self.all_articles)} articles")
        return self.all_articles
    
    def get_page_range(self):
        if not self.all_articles:
            return "1-1"
        
        pages = [article.get('page', 1) for article in self.all_articles]
        min_page = min(pages)
        max_page = max(pages)
        return f"{min_page}-{max_page}"
    
    def save_to_json(self, filename=None):
        if not filename:
            page_range = self.get_page_range()
            article_count = len(self.all_articles)
            filename = f"../data/sciencedaily/sciencedaily_pages_{page_range}_articles_{article_count}.json"
        
        os.makedirs(os.path.dirname(filename), exist_ok=True)
        
        output_data = {
            "metadata": {
                "source": "ScienceDaily AI News",
                "scrape_time": self.scrape_time,
                "total_articles": len(self.all_articles),
                "page_range": self.get_page_range(),
                "scraper_version": "1.0",
                "data_structure": {
                    "fields": ["title", "url", "abstract", "publish_date", "scrape_time", "page"],
                    "description": "ScienceDaily AI news articles with metadata"
                }
            },
            "articles": self.all_articles
        }
        
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(output_data, f, ensure_ascii=False, indent=2)
        
        print(f"data saved to: {filename}")
        print(f"file size: {os.path.getsize(filename) / 1024:.1f} KB")
        return filename

def main():
    parser = argparse.ArgumentParser(description='ScienceDaily scraper with resume, dedup, and progress tracking')
    parser.add_argument('--pages', type=int, default=50, help='number of pages to scrape (default: 50)')
    parser.add_argument('--start', type=int, default=1, help='start page (default: 1)')
    parser.add_argument('--resume', action='store_true', help='resume from last checkpoint')
    parser.add_argument('--clear', action='store_true', help='clear progress file and restart')
    parser.add_argument('--save-interval', type=int, default=5, help='pages between progress saves (default: 5)')
    parser.add_argument('--output', type=str, help='output filename (without extension)')
    
    args = parser.parse_args()
    
    if args.clear:
        if os.path.exists("progress.json"):
            os.remove("progress.json")
            print("progress file cleared")
    
    scraper = ScienceDailyScraper()
    
    if args.resume:
        start_page = 1
        end_page = args.pages
    else:
        start_page = args.start
        end_page = args.start + args.pages - 1
    
    print(f"settings: pages {start_page}-{end_page}, {args.pages} total")
    print(f"save interval: every {args.save_interval} pages")
    
    articles = scraper.scrape_pages(start_page=start_page, end_page=end_page, save_interval=args.save_interval)
    
    if articles:
        if args.output:
            custom_filename = f"../data/sciencedaily/{args.output}.json"
            output_file = scraper.save_to_json(custom_filename)
        else:
            output_file = scraper.save_to_json()
        
        print(f"\n" + "="*50)
        print(f"stats:")
        print(f"total articles: {len(articles)}")
        print(f"page range: {scraper.get_page_range()}")
        print(f"output file: {output_file}")
        print(f"file size: {os.path.getsize(output_file) / 1024:.1f} KB")
        print(f"="*50)
        
        print(f"\nfirst 3 article samples:")
        for i, article in enumerate(articles[:3]):
            print(f"{i+1}. {article['title'][:60]}...")
            print(f"   abstract: {article['abstract'][:80]}...")
            print(f"   published: {article['publish_date']}")
            print(f"   scraped: {article['scrape_time']}")
            print(f"   url: {article['url']}")
            print()
    else:
        print("no article data collected")

if __name__ == "__main__":
    main()
