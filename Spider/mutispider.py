import requests
from bs4 import BeautifulSoup
import json
from datetime import datetime
import re
import time
import random
from concurrent.futures import ThreadPoolExecutor
import logging
import hashlib
import os


class NewsScraperNankaiJSON:
    def __init__(self, output_dir=None):
        # 创建输出目录
        self.output_dir = output_dir or datetime.now().strftime("nankai_news_%Y_%m_%d_%H_%M_%S")
        os.makedirs(self.output_dir, exist_ok=True)

        # 创建子目录
        self.news_dir = os.path.join(self.output_dir, "news")
        self.snapshots_dir = os.path.join(self.output_dir, "snapshots")
        self.attachments_dir = os.path.join(self.output_dir, "attachments")

        os.makedirs(self.news_dir, exist_ok=True)
        os.makedirs(self.snapshots_dir, exist_ok=True)
        os.makedirs(self.attachments_dir, exist_ok=True)

        self.base_url = "http://news.nankai.edu.cn"
        self.first_page = "http://news.nankai.edu.cn/dcxy/index.shtml"
        self.page_template = "https://news.nankai.edu.cn/dcxy/system/count//0005000/000000000000/000/000/c0005000000000000000_000000{:03d}.shtml"
        self.max_pages = 524

        # 计数器
        self.news_index = 0
        self.snapshot_index = 0
        self.attachment_index = 0

        # 统计信息
        self.stats = {
            'total_news': 0,
            'total_snapshots': 0,
            'total_attachments': 0,
            'start_time': datetime.now().isoformat(),
            'processed_pages': 0
        }

        # 支持的附件类型
        self.supported_attachments = [
            ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
            ".mp3", ".mp4", ".avi", ".mkv", ".mov", ".wmv", ".flv",
            ".zip", ".rar", ".tar", ".gz", ".bz2", ".7z",
            ".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tiff",
            ".exe", ".apk", ".dmg", ".csv", ".txt", ".rtf"
        ]

        # 设置日志
        log_filename = os.path.join(self.output_dir, "scraper.log")
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(log_filename, encoding='utf-8'),
                logging.StreamHandler()
            ]
        )

        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Connection': 'keep-alive'
        }

    def get_page_urls(self):
        """生成所有页面的URL"""
        urls = [self.first_page]
        urls.extend(self.page_template.format(i) for i in range(1, self.max_pages + 1))
        return urls

    def get_soup(self, url, retries=3):
        """获取页面的BeautifulSoup对象和原始HTML内容"""
        for i in range(retries):
            try:
                time.sleep(random.uniform(1, 3))
                response = requests.get(url, headers=self.headers, timeout=10)
                response.encoding = 'utf-8'

                if response.status_code == 200:
                    html_content = response.text
                    return BeautifulSoup(html_content, 'html.parser'), html_content
                else:
                    logging.warning(f"Failed to fetch {url}, status code: {response.status_code}")

            except Exception as e:
                logging.error(f"Attempt {i + 1} failed for {url}: {str(e)}")
                if i == retries - 1:
                    logging.error(f"All attempts failed for {url}")
                    return None, None
                time.sleep(random.uniform(2, 5))
        return None, None

    def save_snapshot(self, url, html_content):
        """保存网页快照为JSON文件"""
        try:
            snapshot_data = {
                'id': self.snapshot_index,
                'url': url,
                'html_content': html_content,
                'captured_at': datetime.now().isoformat(),
                'content_hash': hashlib.md5(html_content.encode('utf-8')).hexdigest(),
                'file_size': len(html_content.encode('utf-8'))
            }

            filename = f"snapshot_{self.snapshot_index}.json"
            filepath = os.path.join(self.snapshots_dir, filename)

            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(snapshot_data, f, ensure_ascii=False, indent=2)

            self.snapshot_index += 1
            self.stats['total_snapshots'] += 1
            return snapshot_data['content_hash']

        except Exception as e:
            logging.error(f"Error saving snapshot for {url}: {str(e)}")
            return None

    def find_attachments(self, soup, base_url):
        """查找页面中的附件链接"""
        attachments = []
        for link in soup.find_all('a', href=True):
            href = link['href'].lower()
            if any(ext in href for ext in self.supported_attachments):
                full_url = self.base_url + href if href.startswith('/') else href
                attachments.append({
                    'url': full_url,
                    'filename': os.path.basename(href),
                    'title': link.text.strip(),
                    'extension': os.path.splitext(href)[1].lower()
                })
        return attachments

    def save_attachment_info(self, attachment_info):
        """保存附件信息为JSON文件（不下载实际文件）"""
        try:
            attachment_data = {
                'id': self.attachment_index,
                'url': attachment_info['url'],
                'filename': attachment_info['filename'],
                'title': attachment_info['title'],
                'extension': attachment_info['extension'],
                'discovered_at': datetime.now().isoformat()
            }

            filename = f"attachment_{self.attachment_index}.json"
            filepath = os.path.join(self.attachments_dir, filename)

            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(attachment_data, f, ensure_ascii=False, indent=2)

            self.attachment_index += 1
            self.stats['total_attachments'] += 1
            return self.attachment_index - 1

        except Exception as e:
            logging.error(f"Error saving attachment info {attachment_info['url']}: {str(e)}")
            return None

    def parse_news_list_page(self, url):
        """解析新闻列表页面"""
        soup, html_content = self.get_soup(url)
        if not soup:
            return []

        # 保存列表页快照
        snapshot_hash = self.save_snapshot(url, html_content)
        self.stats['processed_pages'] += 1

        news_items = []
        tables = soup.find_all('table', attrs={'width': "98%", 'border': "0", 'cellpadding': "0", 'cellspacing': "0"})

        for table in tables:
            try:
                title_link = table.find('a')
                if not title_link:
                    continue

                title = title_link.text.strip()
                news_url = self.base_url + title_link['href'] if title_link['href'].startswith('/') else title_link[
                    'href']
                date_td = table.find('td', align="right")
                date = date_td.text.strip() if date_td else None

                logging.info(f"Processing: {title}")

                # 获取新闻详细内容和快照
                article_content, article_snapshot_hash, article_attachments = self.parse_news_detail(news_url)

                news_item = {
                    'id': self.news_index,
                    'title': title,
                    'url': news_url,
                    'date': date,
                    'source': article_content.get('source', ''),
                    'content': article_content.get('content', ''),
                    'content_length': len(article_content.get('content', '')),
                    'snapshot_hash': article_snapshot_hash,
                    'attachments': article_attachments,
                    'crawl_time': datetime.now().isoformat(),
                    'list_page_url': url
                }

                # 保存单个新闻项为JSON文件
                self.save_news_item(news_item)
                news_items.append(news_item)

            except Exception as e:
                logging.error(f"Error parsing news item: {str(e)}")
                continue

        return news_items

    def save_news_item(self, news_item):
        """保存单个新闻项为JSON文件"""
        try:
            filename = f"news_{self.news_index}.json"
            filepath = os.path.join(self.news_dir, filename)

            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(news_item, f, ensure_ascii=False, indent=2)

            self.news_index += 1
            self.stats['total_news'] += 1

        except Exception as e:
            logging.error(f"Error saving news item: {str(e)}")

    def parse_news_detail(self, url):
        """解析新闻详细页面，包括快照和附件"""
        soup, html_content = self.get_soup(url)
        if not soup:
            return {'source': '', 'content': ''}, None, []

        try:
            # 保存快照
            snapshot_hash = self.save_snapshot(url, html_content)

            # 查找附件
            attachments = self.find_attachments(soup, url)
            saved_attachments = []

            # 保存附件信息
            for attachment in attachments:
                attachment_id = self.save_attachment_info(attachment)
                if attachment_id is not None:
                    saved_attachments.append({
                        'attachment_id': attachment_id,
                        'url': attachment['url'],
                        'filename': attachment['filename'],
                        'title': attachment['title'],
                        'extension': attachment['extension']
                    })

            # 解析内容
            source_span = soup.find('span', string=re.compile('来源：'))
            source = source_span.text.strip() if source_span else ''

            content_div = soup.find('td', id='txt')
            if content_div:
                paragraphs = content_div.find_all('p')
                content = '\n'.join([p.text.strip() for p in paragraphs if p.text.strip()])
            else:
                content = ''

            return {
                'source': source,
                'content': content
            }, snapshot_hash, saved_attachments

        except Exception as e:
            logging.error(f"Error parsing detail page {url}: {str(e)}")
            return {'source': '', 'content': ''}, None, []

    def scrape_batch(self, urls, batch_size=10):
        """批量抓取新闻并保存为JSON文件"""
        total_batches = (len(urls) + batch_size - 1) // batch_size

        for i in range(0, len(urls), batch_size):
            batch_urls = urls[i:i + batch_size]
            batch_number = i // batch_size + 1

            logging.info(
                f"Processing batch {batch_number}/{total_batches}, pages {i + 1} to {min(i + batch_size, len(urls))}")

            # 使用线程池并行处理每批URL
            with ThreadPoolExecutor(max_workers=3) as executor:
                batch_results = list(executor.map(self.parse_news_list_page, batch_urls))

            # 合并结果
            batch_news = [item for sublist in batch_results if sublist for item in sublist]

            # 保存批次摘要
            self.save_batch_summary(batch_number, len(batch_news))
            logging.info(f"Batch {batch_number} completed: {len(batch_news)} news items processed")

            # 批次间休息
            time.sleep(random.uniform(3, 5))

    def save_batch_summary(self, batch_number, items_count):
        """保存批次摘要信息"""
        batch_summary = {
            'batch_number': batch_number,
            'items_processed': items_count,
            'timestamp': datetime.now().isoformat(),
            'cumulative_stats': self.stats.copy()
        }

        filename = f"batch_{batch_number}_summary.json"
        filepath = os.path.join(self.output_dir, filename)

        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(batch_summary, f, ensure_ascii=False, indent=2)

    def save_final_summary(self):
        """保存最终统计摘要"""
        self.stats['end_time'] = datetime.now().isoformat()
        self.stats['duration'] = str(datetime.now() - datetime.fromisoformat(self.stats['start_time']))

        # 创建最终摘要
        final_summary = {
            'crawl_summary': self.stats,
            'output_structure': {
                'news_files': f"{self.stats['total_news']} files in {self.news_dir}",
                'snapshot_files': f"{self.stats['total_snapshots']} files in {self.snapshots_dir}",
                'attachment_files': f"{self.stats['total_attachments']} files in {self.attachments_dir}"
            },
            'file_patterns': {
                'news': "news_*.json",
                'snapshots': "snapshot_*.json",
                'attachments': "attachment_*.json",
                'batch_summaries': "batch_*_summary.json"
            }
        }

        filepath = os.path.join(self.output_dir, "final_summary.json")
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(final_summary, f, ensure_ascii=False, indent=2)

        # 创建索引文件便于查询
        self.create_index_files()

    def create_index_files(self):
        """创建索引文件便于查询"""
        # 新闻索引
        news_index = []
        for i in range(self.news_index):
            try:
                filepath = os.path.join(self.news_dir, f"news_{i}.json")
                if os.path.exists(filepath):
                    with open(filepath, 'r', encoding='utf-8') as f:
                        news_data = json.load(f)
                    news_index.append({
                        'id': news_data['id'],
                        'title': news_data['title'],
                        'url': news_data['url'],
                        'date': news_data['date'],
                        'content_length': news_data['content_length'],
                        'file_path': f"news/news_{i}.json"
                    })
            except Exception as e:
                logging.error(f"Error creating index for news_{i}.json: {str(e)}")

        # 保存新闻索引
        index_filepath = os.path.join(self.output_dir, "news_index.json")
        with open(index_filepath, 'w', encoding='utf-8') as f:
            json.dump(news_index, f, ensure_ascii=False, indent=2)

    def scrape(self):
        """主抓取函数"""
        logging.info("Starting to scrape news...")
        urls = self.get_page_urls()
        self.scrape_batch(urls)

        # 保存最终统计信息
        self.save_final_summary()
        logging.info(f"Scraping completed. Total news: {self.stats['total_news']}, "
                     f"Snapshots: {self.stats['total_snapshots']}, "
                     f"Attachments: {self.stats['total_attachments']}")
        logging.info(f"All data saved to: {self.output_dir}")


def main():
    scraper = None
    try:
        scraper = NewsScraperNankaiJSON()
        scraper.scrape()
    except Exception as e:
        logging.error(f"An error occurred during scraping: {str(e)}")
    finally:
        logging.info("Scraping session completed.")


if __name__ == "__main__":
    main()