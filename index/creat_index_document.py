import json
import os
from datetime import datetime
from whoosh.index import create_in
from whoosh.fields import Schema, TEXT, ID, DATETIME
from whoosh.analysis import Tokenizer, Token
import jieba
import shutil
from whoosh.analysis import Tokenizer, Token
import sys
import os
# 将项目根目录添加到 sys.path，以便可以导入 custom_analyzers
# 假设 creat_index_document.py 在 index 文件夹下
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if project_root not in sys.path:
    sys.path.append(project_root)

from custom_analyzers import ChineseAnalyzer, ChineseTokenizer # 新增导入

# --- 中文分词器和分析器 ---
class ChineseTokenizer(Tokenizer):
    def __call__(self, value, positions=True, chars=True, keeporiginal=False,
                 removestops=True, start_pos=0, start_char=0, mode='', **kw):
        assert isinstance(value, str)
        # 使用jieba进行分词
        seg_list = jieba.cut_for_search(value)
        current_pos = 0
        for token_text in seg_list:
            start_char_offset = value.find(token_text, current_pos)
            if start_char_offset == -1:  # Fallback if find fails (e.g. due to case changes by jieba)
                start_char_offset = current_pos

            token = Token()
            token.text = token_text
            token.pos = start_pos + current_pos  # Position in terms of tokens
            if positions:
                token.startchar = start_char + start_char_offset
                token.endchar = start_char + start_char_offset + len(token_text)
            yield token
            current_pos += len(token_text)


class ChineseAnalyzer:
    def __init__(self):
        self.tokenizer = ChineseTokenizer()

    def __call__(self, value, positions=True, chars=True, keeporiginal=False,
                 removestops=True, start_pos=0, start_char=0, mode='', **kw):
        # 返回分词结果的生成器
        return (token for token in self.tokenizer(value, positions=positions, chars=chars,
                                                  keeporiginal=keeporiginal, removestops=removestops,
                                                  start_pos=start_pos, start_char=start_char))


# --- 索引构建器 ---
class JSONIndexBuilder:
    def __init__(self, data_dirs, index_dir="index_dir"):
        self.data_dirs = data_dirs if isinstance(data_dirs, list) else [data_dirs]
        self.index_dir = index_dir
        self.analyzer = ChineseAnalyzer()
        print(f"索引器初始化，数据目录: {self.data_dirs}, 索引将存放在: {self.index_dir}")

    def create_schema(self):
        """创建索引结构"""
        return Schema(
            id=ID(stored=True, unique=True),
            url=ID(stored=True),
            title=TEXT(stored=True, analyzer=self.analyzer, phrase=True),
            content=TEXT(stored=True, analyzer=self.analyzer, phrase=True),  # 用于新闻内容、文档锚文本、页面内容
            publish_date=DATETIME(stored=True),
            source=TEXT(stored=True),  # 主要用于新闻来源
            filename=ID(stored=True),  # 用于文档名
            filetype=ID(stored=True),  # 用于文档类型或页面类型(html)
            crawl_time=DATETIME(stored=True)
        )

    def is_news_directory(self, data_dir_path):
        """判断是否为新闻数据的主目录 (如 nankai_news_...)"""
        if not os.path.exists(data_dir_path) or not os.path.isdir(data_dir_path):
            return False
        # 新闻主目录通常包含 batch_*_summary.json 或 final_summary.json
        # 并且其名称以 "nankai_news_" 开头
        dir_name = os.path.basename(data_dir_path)
        if not dir_name.startswith("nankai_news_"):
            return False

        files = os.listdir(data_dir_path)
        return any(f.startswith("batch_") and f.endswith("_summary.json") for f in files) or \
            any(f == "final_summary.json" for f in files)

    def is_document_or_page_directory(self, data_dir_path):
        """判断是否为文档/页面数据的主目录 (如 download_links_...)"""
        if not os.path.exists(data_dir_path) or not os.path.isdir(data_dir_path):
            return False
        # 文档/页面主目录通常包含 all_documents.json 或 crawl_summary.json 或 documents/pages 子目录
        # 并且其名称以 "download_links_" 开头
        dir_name = os.path.basename(data_dir_path)
        if not dir_name.startswith("download_links_"):
            return False

        has_summary_file = any(f in ["all_documents.json", "crawl_summary.json"] for f in os.listdir(data_dir_path))
        has_subdirs = os.path.exists(os.path.join(data_dir_path, "documents")) or \
                      os.path.exists(os.path.join(data_dir_path, "pages"))
        return has_summary_file or has_subdirs

    def load_news_data(self, news_main_dir):
        """加载新闻数据 (从 news_main_dir/news/ 子目录)"""
        news_data_list = []
        news_content_subdir = os.path.join(news_main_dir, "news")

        if not os.path.exists(news_content_subdir) or not os.path.isdir(news_content_subdir):
            print(f"新闻内容子目录 {news_content_subdir} 不存在或不是目录")
            return news_data_list

        print(f"正在从目录 {news_content_subdir} 加载新闻数据...")
        for filename in os.listdir(news_content_subdir):
            if filename.startswith("news_") and filename.endswith('.json'):
                filepath = os.path.join(news_content_subdir, filename)
                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        data['data_type'] = 'news'
                        news_data_list.append(data)
                except Exception as e:
                    print(f"加载新闻文件 {filepath} 失败: {str(e)}")
        print(f"从 {news_content_subdir} 加载了 {len(news_data_list)} 条新闻数据")
        return news_data_list

    def load_document_data(self, doc_main_dir):
        """加载文档数据 (优先 all_documents.json, 其次 doc_main_dir/documents/ 子目录)"""
        doc_data_list = []

        all_docs_file_path = os.path.join(doc_main_dir, "all_documents.json")
        if os.path.exists(all_docs_file_path):
            print(f"正在从 {all_docs_file_path} 加载所有文档数据...")
            try:
                with open(all_docs_file_path, 'r', encoding='utf-8') as f:
                    documents = json.load(f)
                    for doc_item in documents:
                        doc_item['data_type'] = 'document'
                        doc_data_list.append(doc_item)
                print(f"从 {all_docs_file_path} 加载了 {len(doc_data_list)} 个文档条目")
                return doc_data_list  # 如果成功从all_documents.json加载，则直接返回
            except Exception as e:
                print(f"加载 {all_docs_file_path} 失败: {str(e)}. 将尝试从 documents/ 子目录加载。")

        doc_content_subdir = os.path.join(doc_main_dir, "documents")
        if not os.path.exists(doc_content_subdir) or not os.path.isdir(doc_content_subdir):
            print(f"文档内容子目录 {doc_content_subdir} 不存在或不是目录")
            return doc_data_list  # 如果all_documents.json失败且子目录不存在，返回空

        print(f"正在从目录 {doc_content_subdir} 加载文档数据...")
        for filename in os.listdir(doc_content_subdir):
            if filename.startswith("document_") and filename.endswith('.json'):
                filepath = os.path.join(doc_content_subdir, filename)
                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        data['data_type'] = 'document'
                        doc_data_list.append(data)
                except Exception as e:
                    print(f"加载文档文件 {filepath} 失败: {str(e)}")
        print(f"从 {doc_content_subdir} 加载了 {len(doc_data_list)} 个文档数据")
        return doc_data_list

    def load_page_data(self, page_main_dir):
        """加载通用页面数据 (从 page_main_dir/pages/ 子目录)"""
        page_data_list = []
        page_content_subdir = os.path.join(page_main_dir, "pages")

        if not os.path.exists(page_content_subdir) or not os.path.isdir(page_content_subdir):
            print(f"页面内容子目录 {page_content_subdir} 不存在或不是目录")
            return page_data_list

        print(f"正在从目录 {page_content_subdir} 加载页面数据...")
        for filename in os.listdir(page_content_subdir):
            if filename.startswith("page_") and filename.endswith('.json'):
                filepath = os.path.join(page_content_subdir, filename)
                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        data['data_type'] = 'page'
                        page_data_list.append(data)
                except Exception as e:
                    print(f"加载页面文件 {filepath} 失败: {str(e)}")
        print(f"从 {page_content_subdir} 加载了 {len(page_data_list)} 条页面数据")
        return page_data_list

    def load_json_data(self):
        """加载所有指定数据源的JSON数据"""
        all_data = []
        for data_dir_path in self.data_dirs:
            print(f"开始处理数据目录: {data_dir_path}")
            if self.is_news_directory(data_dir_path):
                print(f"{data_dir_path} 被识别为新闻数据目录。")
                all_data.extend(self.load_news_data(data_dir_path))
            elif self.is_document_or_page_directory(data_dir_path):
                print(f"{data_dir_path} 被识别为文档/页面数据目录。")
                all_data.extend(self.load_document_data(data_dir_path))
                all_data.extend(self.load_page_data(data_dir_path))  # 文档目录也可能包含页面数据
            else:
                print(f"警告: 目录 {data_dir_path} 未被识别为已知数据类型目录，跳过。")

        print(f"所有目录处理完毕，总共加载了 {len(all_data)} 条记录。")
        return all_data

    def parse_date(self, date_str):
        """解析日期字符串，支持多种格式"""
        if not date_str or not isinstance(date_str, str):
            return None

        # 常见日期格式列表
        formats_to_try = [
            '%Y-%m-%dT%H:%M:%S.%fZ', '%Y-%m-%dT%H:%M:%SZ',  # ISO 8601 with Z
            '%Y-%m-%dT%H:%M:%S.%f', '%Y-%m-%dT%H:%M:%S',  # ISO 8601 without Z
            '%Y-%m-%d %H:%M:%S',
            '%Y-%m-%d',
            '%Y/%m/%d %H:%M:%S',
            '%Y/%m/%d',
            '%Y年%m月%d日 %H时%M分%S秒',
            '%Y年%m月%d日',
        ]

        # 尝试移除可能的时区信息 (如 +08:00) 以简化解析
        if '+' in date_str:
            date_str = date_str.split('+')[0]
        if '.' in date_str and len(date_str.split('.')[-1]) > 6 and date_str.endswith(
                'Z'):  # handle over-precise microseconds
            parts = date_str.split('.')
            date_str = parts[0] + '.' + parts[1][:6] + 'Z'

        for fmt in formats_to_try:
            try:
                return datetime.strptime(date_str, fmt)
            except (ValueError, TypeError):
                continue

        # 作为最后的尝试，如果它是纯数字且长度合适，尝试解析为时间戳
        if date_str.isdigit():
            try:
                timestamp = float(date_str)
                # 假设是秒级时间戳
                if len(date_str) >= 10 and len(date_str) <= 11:  # typical range for seconds timestamp
                    return datetime.fromtimestamp(timestamp)
                # 假设是毫秒级时间戳
                elif len(date_str) >= 13 and len(date_str) <= 14:
                    return datetime.fromtimestamp(timestamp / 1000.0)
            except ValueError:
                pass

        print(f"日期解析失败，无法识别格式: {date_str}")
        return None

    def build_index(self):
        """构建索引"""
        if os.path.exists(self.index_dir):
            print(f"索引目录 {self.index_dir} 已存在，将删除并重建。")
            shutil.rmtree(self.index_dir)
        os.makedirs(self.index_dir)
        print(f"创建新的索引目录: {self.index_dir}")

        schema = self.create_schema()
        ix = create_in(self.index_dir, schema)
        writer = ix.writer(procs=os.cpu_count(), limitmb=512, multisegment=True)  # 优化写入性能
        print("索引写入器已创建。")

        data_list = self.load_json_data()
        if not data_list:
            print("没有加载到任何数据，索引构建中止。")
            return

        print(f"开始为 {len(data_list)} 条记录构建索引...")
        processed_ids = set()  # 用于检测重复ID

        for i, item_data in enumerate(data_list):
            try:
                item_id_str = str(item_data.get('id', f"auto_id_{i}"))
                if item_id_str in processed_ids:
                    print(
                        f"警告: 检测到重复ID '{item_id_str}'，记录将被跳过。数据: {item_data.get('url', item_data.get('title', 'N/A'))}")
                    item_id_str = f"{item_id_str}_dup_{i}"  # 尝试生成一个唯一的ID
                    if item_id_str in processed_ids:  # 如果还是重复，就真的跳过
                        print(f"警告: 尝试生成唯一ID后仍然重复 '{item_id_str}'，记录将被跳过。")
                        continue
                processed_ids.add(item_id_str)

                doc_to_index = {
                    'id': item_id_str,
                    'url': item_data.get('url', ''),
                    'title': item_data.get('title', ''),
                    'source': item_data.get('source', ''),  # 主要用于新闻
                    'crawl_time': self.parse_date(item_data.get('crawl_time')),
                    'publish_date': self.parse_date(item_data.get('date')),  # 新闻的 'date' 字段
                    'filename': '',  # 默认值
                    'filetype': ''  # 默认值
                }

                data_type = item_data.get('data_type')
                if data_type == 'news':
                    doc_to_index['content'] = item_data.get('content', '')
                    doc_to_index['filetype'] = 'html'
                elif data_type == 'document':
                    # 根据作业要求，文档索引锚文本
                    doc_to_index['content'] = item_data.get('anchor_text', '')
                    doc_to_index['filename'] = item_data.get('file_name', item_data.get('filename', ''))
                    doc_to_index['filetype'] = item_data.get('file_type', item_data.get('extension', '')).replace('.',
                                                                                                                  '')
                elif data_type == 'page':
                    doc_to_index['content'] = item_data.get('content', '')  # page_*.json 可能没有 'content'
                    doc_to_index['filetype'] = 'html'
                else:
                    doc_to_index['content'] = item_data.get('content', '')  # 未知类型的默认处理
                    print(f"警告: 未知数据类型 '{data_type}' 对于 ID '{item_id_str}'")

                # 如果 publish_date 为空，但 crawl_time 存在，可以考虑使用 crawl_time
                if not doc_to_index['publish_date'] and doc_to_index['crawl_time']:
                    doc_to_index['publish_date'] = doc_to_index['crawl_time']

                writer.add_document(**doc_to_index)

                if (i + 1) % 1000 == 0:
                    print(f"已处理 {i + 1} / {len(data_list)} 条记录...")

            except Exception as e:
                print(
                    f"索引记录 {i} (ID: {item_data.get('id', 'N/A')}, URL: {item_data.get('url', 'N/A')}) 时发生严重错误: {str(e)}")
                # import traceback
                # traceback.print_exc() # 取消注释以获取详细的堆栈跟踪
                continue

        print("所有记录处理完毕，正在提交写入器...")
        writer.commit()
        print(f"索引构建完成！总共索引了 {ix.doc_count()} 个文档。")


def main():
    # 自动检测Spider目录下的数据文件夹
    # 项目根目录的相对路径，假设此脚本在 index/ 目录下
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    spider_dir = os.path.join(project_root, "Spider")

    detected_data_dirs = []
    if os.path.exists(spider_dir) and os.path.isdir(spider_dir):
        print(f"正在扫描数据目录: {spider_dir}")
        for item_name in os.listdir(spider_dir):
            item_full_path = os.path.join(spider_dir, item_name)
            if os.path.isdir(item_full_path):
                if item_name.startswith("nankai_news_") or item_name.startswith("download_links_"):
                    detected_data_dirs.append(item_full_path)
                    print(f"  检测到数据文件夹: {item_full_path}")
    else:
        print(f"Spider目录 {spider_dir} 未找到。")

    if not detected_data_dirs:
        print("未能自动检测到数据目录，将使用默认的硬编码路径。")
        # 注意：硬编码的绝对路径可能因环境而异，自动检测更佳
        # 使用原始字符串以避免转义问题
        default_base_path = r"D:\桌面\Web-Search-Engine-main\Spider"
        detected_data_dirs = [
            os.path.join(default_base_path, "nankai_news_2025_05_29_00_39_58"),
            os.path.join(default_base_path, "download_links_2025_05_29_07_45_08")
        ]
        # 验证默认路径是否存在
        valid_default_dirs = [d for d in detected_data_dirs if os.path.exists(d)]
        if not valid_default_dirs:
            print("错误：默认的数据目录也不存在，请检查路径配置。索引构建中止。")
            return
        detected_data_dirs = valid_default_dirs

    print(f"最终用于索引的数据目录列表: {detected_data_dirs}")

    # 构建统一索引
    # 索引目录将创建在当前脚本所在目录下，名为 "index_dir"
    index_output_dir = os.path.join(os.path.dirname(__file__), "index_dir")
    builder = JSONIndexBuilder(data_dirs=detected_data_dirs, index_dir=index_output_dir)
    builder.build_index()


if __name__ == "__main__":
    # 初始化jieba，避免多线程问题（如果writer使用多进程）
    # 对于搜索，通常在Web应用启动时初始化一次即可
    jieba.initialize()
    main()