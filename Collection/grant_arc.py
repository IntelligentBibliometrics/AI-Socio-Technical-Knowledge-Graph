import argparse
import time
import json
import os
from datetime import datetime
import logging

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import NoSuchElementException

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class ARCGrantsScraper:
    def __init__(self, output_dir=None):
        self.total_pages = 34
        self.total_expected_records = 33362
        self.max_records_per_page = 1000
        self.output_dir = output_dir or os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")
        self.progress_file = os.path.join(self.output_dir, "scraping_progress.json")
        self.driver = None
        
        os.makedirs(self.output_dir, exist_ok=True)
    
    def save_progress(self, page_num, all_data, completed_pages):
        progress_data = {
            "last_completed_page": page_num,
            "total_records_scraped": len(all_data),
            "completed_pages": completed_pages,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "data": all_data
        }
        
        with open(self.progress_file, 'w', encoding='utf-8') as f:
            json.dump(progress_data, f, ensure_ascii=False, indent=2)
        
        logger.info(f"Progress saved: Page {page_num}, {len(all_data)} records")
    
    def load_progress(self):
        if os.path.exists(self.progress_file):
            try:
                with open(self.progress_file, 'r', encoding='utf-8') as f:
                    progress_data = json.load(f)
                
                logger.info(f"Found previous progress: Page {progress_data['last_completed_page']}, {progress_data['total_records_scraped']} records")
                return progress_data
            except Exception as e:
                logger.error(f"Error loading progress: {e}")
                return None
        return None
    
    def calculate_page_records(self, page_num):
        if page_num < self.total_pages:
            return self.max_records_per_page
        else:
            remaining_records = self.total_expected_records - (self.total_pages - 1) * self.max_records_per_page
            return remaining_records
    
    def init_driver(self):
        try:
            chrome_options = Options()
            chrome_options.add_argument('--start-maximized')
            chrome_options.add_argument('--disable-blink-features=AutomationControlled')
            chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
            chrome_options.add_experimental_option('useAutomationExtension', False)
            
            self.driver = webdriver.Chrome(options=chrome_options)
            self.driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            return True
        except Exception as e:
            logger.error(f"Failed to initialize driver: {e}")
            return False
    
    def refresh_page_and_wait(self, url, wait_time=15):
        try:
            logger.info("Refreshing page...")
            self.driver.refresh()
            time.sleep(wait_time)
            
            wait = WebDriverWait(self.driver, 30)
            wait.until(EC.presence_of_element_located((By.XPATH, "/html/body/main/div[1]/section[2]/div/div/div[2]/div[4]")))
            
            logger.info("Page refreshed and loaded successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to refresh page: {e}")
            return False
    
    def scrape_single_record(self, page_num, record_num):
        try:
            title_xpath = f"/html/body/main/div[1]/section[2]/div/div/div[2]/div[4]/article[{record_num}]/h3/a"
            title_element = self.driver.find_element(By.XPATH, title_xpath)
            
            project_info = title_element.text.strip()
            project_link = title_element.get_attribute('href')
            
            if " — " in project_info:
                project_number = project_info.split(" — ")[0].strip()
                institution_name = project_info.split(" — ")[1].strip()
            else:
                project_number = project_info
                institution_name = "Institution name not available"
            
            fields = {
                'description': f"/html/body/main/div[1]/section[2]/div/div/div[2]/div[4]/article[{record_num}]/p",
                'scheme_name': f"/html/body/main/div[1]/section[2]/div/div/div[2]/div[4]/article[{record_num}]/ul/li[2]/span[2]",
                'lead_investigator': f"/html/body/main/div[1]/section[2]/div/div/div[2]/div[4]/article[{record_num}]/ul/li[3]/span[2]",
                'current_funding': f"/html/body/main/div[1]/section[2]/div/div/div[2]/div[4]/article[{record_num}]/ul/li[4]/span[2]",
                'announced_funding': f"/html/body/main/div[1]/section[2]/div/div/div[2]/div[4]/article[{record_num}]/ul/li[5]/span[2]",
                'commencement_year': f"/html/body/main/div[1]/section[2]/div/div/div[2]/div[4]/article[{record_num}]/ul/li[6]/span[2]",
                'status': f"/html/body/main/div[1]/section[2]/div/div/div[2]/div[4]/article[{record_num}]/ul/li[7]/span[2]",
                'primary_for': f"/html/body/main/div[1]/section[2]/div/div/div[2]/div[4]/article[{record_num}]/ul/li[8]/span[2]"
            }
            
            field_values = {}
            for field_name, xpath in fields.items():
                try:
                    element = self.driver.find_element(By.XPATH, xpath)
                    field_values[field_name] = element.text.strip()
                except Exception:
                    field_values[field_name] = f"{field_name.replace('_', ' ').title()} retrieval failed"
            
            global_record_number = (page_num - 1) * self.max_records_per_page + record_num
            
            record_data = {
                'Global Record Number': global_record_number,
                'Page Number': page_num,
                'Page Record Number': record_num,
                'Project Number': project_number,
                'Institution Name': institution_name,
                'Project Description': field_values['description'],
                'Scheme Name': field_values['scheme_name'],
                'Lead Investigator': field_values['lead_investigator'],
                'Current Funding': field_values['current_funding'],
                'Announced Funding': field_values['announced_funding'],
                'Funding Commencement Year': field_values['commencement_year'],
                'Status': field_values['status'],
                'Primary FoR': field_values['primary_for'],
                'Link': project_link
            }
            
            return record_data
            
        except NoSuchElementException:
            return None
        except Exception as e:
            logger.warning(f"Error scraping record {record_num} on page {page_num}: {e}")
            return None
    
    def scrape_page(self, page_num, max_retries=3, max_refresh_retries=2):
        url = f"https://dataportal.arc.gov.au/NCGP/Web/Grant/Grants#/1000/{page_num}/"
        
        for attempt in range(max_retries):
            try:
                if attempt == 0:
                    self.driver.get(url)
                    logger.info(f"Loading page {page_num}/{self.total_pages} (Attempt {attempt + 1})")
                else:
                    logger.info(f"Retrying page {page_num}/{self.total_pages} (Attempt {attempt + 1})")
                
                wait = WebDriverWait(self.driver, 30)
                time.sleep(10)
                
                page_data = []
                expected_records = self.calculate_page_records(page_num)
                consecutive_failures = 0
                page_error_count = 0
                refresh_attempts = 0
                
                for record_num in range(1, expected_records + 1):
                    record_data = self.scrape_single_record(page_num, record_num)
                    
                    if record_data:
                        page_data.append(record_data)
                        consecutive_failures = 0
                        page_error_count = 0
                        
                        if record_num % 100 == 0 or record_num <= 5:
                            logger.info(f"Page {page_num} - Record {record_num}/{expected_records}: {record_data['Project Number']}")
                    else:
                        consecutive_failures += 1
                        page_error_count += 1
                        
                        if page_error_count >= 20 and refresh_attempts < max_refresh_retries:
                            logger.warning(f"Page {page_num}: {page_error_count} consecutive errors detected, attempting page refresh...")
                            
                            if self.refresh_page_and_wait(url):
                                refresh_attempts += 1
                                page_error_count = 0
                                consecutive_failures = 0
                                logger.info(f"Page {page_num} refreshed successfully, continuing from record {record_num}")
                                
                                record_data = self.scrape_single_record(page_num, record_num)
                                if record_data:
                                    page_data.append(record_data)
                                    if record_num % 100 == 0 or record_num <= 5:
                                        logger.info(f"Page {page_num} - Record {record_num}/{expected_records}: {record_data['Project Number']} (after refresh)")
                                    continue
                            else:
                                logger.error(f"Failed to refresh page {page_num}, continuing with errors...")
                        
                        if consecutive_failures >= 10:
                            logger.info(f"Reached end of page {page_num} at record {record_num}")
                            break
                
                completion_rate = len(page_data) / expected_records * 100
                logger.info(f"Page {page_num} completed: {len(page_data)}/{expected_records} records scraped ({completion_rate:.1f}%)")
                
                if completion_rate < 80 and refresh_attempts < max_refresh_retries and attempt < max_retries - 1:
                    logger.warning(f"Page {page_num} completion rate too low ({completion_rate:.1f}%), will retry entire page...")
                    if self.refresh_page_and_wait(url):
                        continue
                
                return page_data
                
            except Exception as e:
                logger.error(f"Error on page {page_num}, attempt {attempt + 1}: {e}")
                if attempt < max_retries - 1:
                    logger.info(f"Retrying page {page_num} in 30 seconds...")
                    time.sleep(30)
                    
                    if not self.refresh_page_and_wait(url):
                        logger.info("Page refresh failed, reinitializing driver...")
                        if self.driver:
                            self.driver.quit()
                        if not self.init_driver():
                            raise Exception("Failed to reinitialize driver")
                else:
                    logger.error(f"Failed to scrape page {page_num} after {max_retries} attempts")
                    return []
        
        return []
    
    def scrape_all_pages(self, start_page=1, resume=True):
        all_grants_data = []
        completed_pages = []
        
        if resume:
            progress = self.load_progress()
            if progress:
                all_grants_data = progress.get('data', [])
                completed_pages = progress.get('completed_pages', [])
                start_page = progress.get('last_completed_page', 0) + 1
                logger.info(f"Resuming from page {start_page}, already have {len(all_grants_data)} records")
        
        if not self.init_driver():
            logger.error("Failed to initialize browser driver")
            return
        
        try:
            for page_num in range(start_page, self.total_pages + 1):
                if page_num in completed_pages:
                    logger.info(f"Page {page_num} already completed, skipping...")
                    continue
                
                page_data = self.scrape_page(page_num)
                
                if page_data:
                    all_grants_data.extend(page_data)
                    completed_pages.append(page_num)
                    
                    self.save_progress(page_num, all_grants_data, completed_pages)
                    
                    logger.info(f"Total records so far: {len(all_grants_data)}")
                    
                    if page_num % 5 == 0:
                        logger.info("Taking a 60-second break...")
                        time.sleep(60)
                else:
                    logger.warning(f"No data retrieved from page {page_num}")
            
            self.save_final_results(all_grants_data)
            
        except KeyboardInterrupt:
            logger.info("Scraping interrupted by user. Progress has been saved.")
        except Exception as e:
            logger.error(f"Unexpected error during scraping: {e}")
        finally:
            if self.driver:
                self.driver.quit()
    
    def save_final_results(self, all_data):
        json_filename = "ARC_grants_complete.json"
        json_filepath = os.path.join(self.output_dir, json_filename)
        
        final_data = {
            "Scraping Time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "Total Pages Scraped": self.total_pages,
            "Total Records": len(all_data),
            "Expected Records": self.total_expected_records,
            "Completion Rate": f"{len(all_data)/self.total_expected_records*100:.2f}%",
            "Data Content": all_data
        }
        
        with open(json_filepath, 'w', encoding='utf-8') as f:
            json.dump(final_data, f, ensure_ascii=False, indent=2)
        
        logger.info(f"=== SCRAPING COMPLETED ===")
        logger.info(f"Total records scraped: {len(all_data)}/{self.total_expected_records}")
        logger.info(f"Final dataset saved to: {json_filepath}")

def main():
    ap = argparse.ArgumentParser(description="Scrape ARC NCGP grants (Selenium).")
    ap.add_argument("--outdir", default=None,
                    help="输出目录 (默认: 脚本旁的 ./output)")
    ap.add_argument("--no-resume", action="store_true",
                    help="忽略已有进度, 从头开始 (默认自动续传)")
    args = ap.parse_args()

    scraper = ARCGrantsScraper(output_dir=args.outdir)
    logger.info("ARC grants scraper | pages=%d expected=%d | outdir=%s | resume=%s",
                scraper.total_pages, scraper.total_expected_records,
                scraper.output_dir, not args.no_resume)
    scraper.scrape_all_pages(resume=not args.no_resume)

if __name__ == "__main__":
    main()

