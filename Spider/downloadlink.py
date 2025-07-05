import json
import os
import re
import time
import requests
from bs4 import BeautifulSoup
from datetime import datetime
import logging
from urllib.parse import urljoin, urlparse


class DownloadLinkCrawlerJSON:
    def __init__(self, output_dir=None):
        # 创建输出目录
        self.output_dir = output_dir or datetime.now().strftime("download_links_%Y_%m_%d_%H_%M_%S")
        os.makedirs(self.output_dir, exist_ok=True)

        # 创建子目录
        self.documents_dir = os.path.join(self.output_dir, "documents")
        self.pages_dir = os.path.join(self.output_dir, "pages")

        os.makedirs(self.documents_dir, exist_ok=True)
        os.makedirs(self.pages_dir, exist_ok=True)

        # 配置日志
        log_filename = os.path.join(self.output_dir, "crawler.log")
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s - %(levelname)s - %(message)s",
            handlers=[
                logging.StreamHandler(),
                logging.FileHandler(log_filename, mode="w", encoding="utf-8")
            ]
        )

        # 设置头信息
        self.headers = {
            'Connection': 'Keep-Alive',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Accept-Encoding': 'gzip, deflate',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }

        # 下载文档后缀列表
        self.download_extensions = {
            "pdf", "doc", "docx", "xls", "xlsx", "ppt", "pptx",
            "mp3", "mp4", "avi", "mkv", "mov", "wmv", "flv",
            "zip", "rar", "tar", "gz", "bz2", "7z",
            "jpg", "jpeg", "png", "gif", "bmp", "tiff",
            "exe", "apk", "dmg", "csv", "txt", "rtf"
        }

        # 计数器和统计
        self.document_counter = 0
        self.page_counter = 0
        self.crawled_urls = set()

        self.stats = {
            'start_time': datetime.now().isoformat(),
            'total_pages_crawled': 0,
            'total_documents_found': 0,
            'document_types': {},
            'crawl_depth': 0
        }

    def get_html(self, url, timeout=10):
        """获取网页内容"""
        try:
            logging.info(f"Fetching: {url}")
            response = requests.get(url, timeout=timeout, headers=self.headers, allow_redirects=True)
            response.encoding = response.apparent_encoding or 'utf-8'
            return response.text
        except Exception as e:
            logging.error(f"Failed to fetch {url}: {str(e)}")
            return ""

    def is_nankai_url(self, url):
        """检查是否为南开大学域名"""
        try:
            parsed = urlparse(url)
            return 'nankai' in parsed.netloc.lower()
        except:
            return False

    def extract_links_and_documents(self, soup, base_url):
        """提取页面中的链接和文档"""
        page_links = []
        documents = []

        for item in soup.find_all("a", href=True):
            href = item.get("href")
            if not href:
                continue

            # 清理链接
            href = str(href)
            if '#' in href:
                href = href[:href.find("#")]

            if href.find("javascript") != -1 or len(href) < 1 or href == '/':
                continue

            # 构建完整URL
            full_url = urljoin(base_url, href)

            # 检查是否为南开域名
            if not self.is_nankai_url(full_url):
                continue

            # 过滤特定URL
            if any(skip in full_url for skip in [
                "less.nankai.edu.cn/public",
                "weekly.nankai.edu.cn/oldrelease.php"
            ]):
                continue

            # 获取文件扩展名
            parsed_url = urlparse(full_url)
            path = parsed_url.path
            extension = os.path.splitext(path)[1][1:].lower()  # 去掉点号

            # 如果是文档链接
            if extension in self.download_extensions:
                file_title = item.get_text().strip() or "Unknown Title"

                document_info = {
                    "id": self.document_counter,
                    "url": full_url,
                    "title": file_title,
                    "file_type": extension,
                    "file_name": os.path.basename(path),
                    "anchor_text": file_title,
                    "source_page": base_url,
                    "file_size_estimate": "unknown",
                    "crawl_time": datetime.now().isoformat()
                }

                documents.append(document_info)

                # 保存单个文档信息
                self.save_document_info(document_info)

                # 更新统计
                self.stats['total_documents_found'] += 1
                if extension in self.stats['document_types']:
                    self.stats['document_types'][extension] += 1
                else:
                    self.stats['document_types'][extension] = 1

                logging.info(f"[{self.document_counter}] Document found: {file_title[:50]}... ({extension})")
                self.document_counter += 1
            else:
                # 普通页面链接
                page_links.append(full_url)

        return page_links, documents

    def save_document_info(self, document_info):
        """保存单个文档信息"""
        filename = f"document_{document_info['id']}.json"
        filepath = os.path.join(self.documents_dir, filename)

        with open(filepath, 'w', encoding="utf-8") as f:
            json.dump(document_info, f, ensure_ascii=False, indent=2)

    def save_page_info(self, url, title, content_length, links_count, documents_count):
        """保存页面信息"""
        page_info = {
            "id": self.page_counter,
            "url": url,
            "title": title,
            "content_length": content_length,
            "links_found": links_count,
            "documents_found": documents_count,
            "crawl_time": datetime.now().isoformat()
        }

        filename = f"page_{self.page_counter}.json"
        filepath = os.path.join(self.pages_dir, filename)

        with open(filepath, 'w', encoding="utf-8") as f:
            json.dump(page_info, f, ensure_ascii=False, indent=2)

        self.page_counter += 1
        self.stats['total_pages_crawled'] += 1

    def crawl_recursive(self, urls, max_depth=6, current_depth=0, max_total_pages=30000):
        """递归爬取"""
        if current_depth >= max_depth or self.stats['total_pages_crawled'] >= max_total_pages:
            logging.info(f"Stopping crawl: depth={current_depth}, pages={self.stats['total_pages_crawled']}")
            return

        self.stats['crawl_depth'] = max(self.stats['crawl_depth'], current_depth)
        next_level_urls = []

        logging.info(f"Crawling depth {current_depth}, {len(urls)} URLs to process")

        for url in urls:
            if url in self.crawled_urls or self.stats['total_pages_crawled'] >= max_total_pages:
                continue

            try:
                html_content = self.get_html(url)
                if not html_content:
                    continue

                soup = BeautifulSoup(html_content, "html.parser")

                # 提取页面标题
                title = soup.title.get_text().strip() if soup.title else "No Title"

                # 提取链接和文档
                page_links, documents = self.extract_links_and_documents(soup, url)

                # 保存页面信息
                self.save_page_info(url, title, len(html_content), len(page_links), len(documents))

                # 添加到已爬取集合
                self.crawled_urls.add(url)

                # 收集下一层要爬取的URL
                for link in page_links:
                    if link not in self.crawled_urls and link not in next_level_urls:
                        next_level_urls.append(link)

                # 进度报告
                if self.stats['total_pages_crawled'] % 100 == 0:
                    logging.info(f"Progress: {self.stats['total_pages_crawled']} pages, "
                                 f"{self.stats['total_documents_found']} documents")

                # 礼貌爬取延时
                time.sleep(1)

            except Exception as e:
                logging.error(f"Error processing {url}: {str(e)}")
                continue

        # 递归到下一层
        if next_level_urls and current_depth < max_depth - 1:
            # 限制下一层URL数量避免过度扩展
            next_level_urls = next_level_urls[:500]
            self.crawl_recursive(next_level_urls, max_depth, current_depth + 1, max_total_pages)

    def save_final_summary(self):
        """保存最终统计摘要"""
        self.stats['end_time'] = datetime.now().isoformat()

        # 计算爬取时长
        start_time = datetime.fromisoformat(self.stats['start_time'])
        end_time = datetime.fromisoformat(self.stats['end_time'])
        self.stats['duration'] = str(end_time - start_time)

        # 创建汇总文档索引
        all_documents = []
        for i in range(self.document_counter):
            doc_path = os.path.join(self.documents_dir, f"document_{i}.json")
            if os.path.exists(doc_path):
                with open(doc_path, 'r', encoding='utf-8') as f:
                    all_documents.append(json.load(f))

        # 保存完整的文档列表
        with open(os.path.join(self.output_dir, "all_documents.json"), 'w', encoding='utf-8') as f:
            json.dump(all_documents, f, ensure_ascii=False, indent=2)

        # 保存统计摘要
        summary = {
            'crawl_stats': self.stats,
            'output_structure': {
                'total_files_created': self.document_counter + self.page_counter + 2,
                'documents_directory': f"{self.documents_dir} ({self.document_counter} files)",
                'pages_directory': f"{self.pages_dir} ({self.page_counter} files)",
                'summary_files': ["all_documents.json", "crawl_summary.json"]
            },
            'document_type_distribution': self.stats['document_types']
        }

        with open(os.path.join(self.output_dir, "crawl_summary.json"), 'w', encoding='utf-8') as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)

    def start_crawling(self, start_urls=None):
        """开始爬取"""
        # 默认起始URL
        if start_urls is None:
            try:
                with open("default_urls_download.json", 'r', encoding='utf-8') as f:
                    start_urls = json.load(f)
            except:
                start_urls = [
                    "http://news.nankai.edu.cn",
                    "http://www.nankai.edu.cn",
                    "http://jwc.nankai.edu.cn",
                    "http://lib.nankai.edu.cn"
                ]

        logging.info(f"Starting crawl with {len(start_urls)} URLs")
        logging.info(f"Output directory: {self.output_dir}")

        # 开始递归爬取
        self.crawl_recursive(start_urls)

        # 保存最终摘要
        self.save_final_summary()

        logging.info("Crawling completed!")
        logging.info(f"Total pages crawled: {self.stats['total_pages_crawled']}")
        logging.info(f"Total documents found: {self.stats['total_documents_found']}")
        logging.info(f"Output saved to: {self.output_dir}")


def main():
    crawler = DownloadLinkCrawlerJSON()
    crawler.start_crawling()


if __name__ == "__main__":
    main()