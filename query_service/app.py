import os
import json
from whoosh.query import Wildcard, Or
from datetime import datetime
from flask import Flask, render_template, request, abort
from whoosh.index import open_dir
from whoosh.qparser import QueryParser, MultifieldParser, WildcardPlugin, PhrasePlugin, FieldsPlugin
from whoosh.query import Term, And, Or, Not, Prefix, TermRange
from whoosh.searching import ResultsPage
import jieba
import sys
import os
from urllib.parse import quote
from whoosh.query import Phrase, Or
import re
from custom_analyzers import ChineseAnalyzer, ChineseTokenizer # 新增导入

# 在现有的导入部分修改/添加这一行
from whoosh.query import Term, And, Or, Not, Prefix, TermRange, Wildcard, Regex
# 在文件顶部添加导入
from flask import Flask, render_template, request, abort, session, redirect, url_for, flash
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3
from functools import wraps
# 在配置部分添加
# --- Flask 应用初始化 ---
app = Flask(__name__)
jieba.initialize() # 初始化Jieba

# 用户数据库文件路径
USER_DB_FILE = "users.db"
# 将项目根目录添加到 sys.path
# 假设 app.py 在 query_service 文件夹下
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if project_root not in sys.path:
    sys.path.append(project_root)
# 特殊处理中文短语查询


# --- 配置 (使用绝对路径) ---
# !!! 如果项目位置改变，这些路径需要手动更新 !!!
INDEX_DIR = os.path.join("..", "index", "index_dir") # Whoosh 索引目录
QUERY_LOG_FILE = "query_log.txt" # 查询日志文件

# 新闻快照数据相关的绝对路径
NEWS_DATA_BASE_DIR = os.path.join("..", "Spider")# 爬虫数据根目录
# 默认的新闻爬取子目录名 (仍然是子目录名，不是完整路径)
# 这个值会与 NEWS_DATA_BASE_DIR 结合使用
DEFAULT_NEWS_CRAWL_SUBDIR = "nankai_news_2025_05_29_00_39_58" # 示例新闻爬取子目录名

# BASE_DIR 变量如果其他地方没有用到，可以移除。
# 如果其他地方（例如模板中构建URL或静态文件路径）间接用到了 BASE_DIR 的概念，
PROJECT_ROOT_DIR = "Web-Search-Engine-main"


app.secret_key = 'nankai_search_engine_2024'  # 用于session加密
# --- Whoosh 索引加载 ---
try:
    ix = open_dir(INDEX_DIR)
    print(f"Successfully opened Whoosh index at {INDEX_DIR}")
except Exception as e:
    print(f"Error opening Whoosh index at {INDEX_DIR}: {e}")
    ix = None

# --- 辅助函数 ---
# 在辅助函数部分添加
# 在app.py中添加个性化推荐功能

def get_user_search_patterns(user_id, limit=50):
    """获取用户搜索模式"""
    conn = sqlite3.connect(USER_DB_FILE)
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT query, COUNT(*) as frequency, MAX(timestamp) as last_search
        FROM user_queries 
        WHERE user_id = ? 
        GROUP BY query 
        ORDER BY frequency DESC, last_search DESC 
        LIMIT ?
    ''', (user_id, limit))
    
    patterns = cursor.fetchall()
    conn.close()
    return patterns

def get_related_queries(base_query, user_id=None, limit=5):
    """获取相关查询推荐"""
    recommendations = []
    
    try:
        conn = sqlite3.connect(USER_DB_FILE)
        cursor = conn.cursor()
        
        # 方法1: 基于用户历史的相似查询
        if user_id:
            cursor.execute('''
                SELECT DISTINCT query, COUNT(*) as freq
                FROM user_queries 
                WHERE user_id = ? AND query LIKE ? AND query != ?
                GROUP BY query
                ORDER BY freq DESC
                LIMIT ?
            ''', (user_id, f'%{base_query}%', base_query, limit))
            
            user_related = cursor.fetchall()
            recommendations.extend([q[0] for q in user_related])
        
        # 方法2: 基于所有用户的热门相关查询
        cursor.execute('''
            SELECT query, COUNT(*) as freq
            FROM user_queries 
            WHERE query LIKE ? AND query != ?
            GROUP BY query
            ORDER BY freq DESC
            LIMIT ?
        ''', (f'%{base_query}%', base_query, limit * 2))
        
        global_related = cursor.fetchall()
        
        # 合并推荐，去重
        for q in global_related:
            if q[0] not in recommendations and len(recommendations) < limit:
                recommendations.append(q[0])
        
        conn.close()
        
    except Exception as e:
        print(f"Error getting related queries: {e}")
    
    return recommendations

def get_search_suggestions(query_prefix, user_id=None, limit=10):
    """获取搜索建议（自动完成）"""
    suggestions = []
    
    try:
        conn = sqlite3.connect(USER_DB_FILE)
        cursor = conn.cursor()
        
        # 优先显示用户自己的历史查询
        if user_id:
            cursor.execute('''
                SELECT DISTINCT query, COUNT(*) as freq
                FROM user_queries 
                WHERE user_id = ? AND query LIKE ?
                GROUP BY query
                ORDER BY freq DESC, MAX(timestamp) DESC
                LIMIT ?
            ''', (user_id, f'{query_prefix}%', limit // 2))
            
            user_suggestions = [row[0] for row in cursor.fetchall()]
            suggestions.extend(user_suggestions)
        
        # 补充全局热门查询
        cursor.execute('''
            SELECT query, COUNT(*) as freq
            FROM user_queries 
            WHERE query LIKE ?
            GROUP BY query
            ORDER BY freq DESC
            LIMIT ?
        ''', (f'{query_prefix}%', limit))
        
        global_suggestions = [row[0] for row in cursor.fetchall()]
        
        # 合并去重
        for suggestion in global_suggestions:
            if suggestion not in suggestions and len(suggestions) < limit:
                suggestions.append(suggestion)
        
        conn.close()
        
    except Exception as e:
        print(f"Error getting search suggestions: {e}")
    
    return suggestions

def get_trending_queries(limit=10):
    """获取热门/趋势查询"""
    try:
        conn = sqlite3.connect(USER_DB_FILE)
        cursor = conn.cursor()
        
        # 获取最近7天的热门查询
        cursor.execute('''
            SELECT query, COUNT(*) as freq
            FROM user_queries 
            WHERE timestamp > datetime('now', '-7 days')
            GROUP BY query
            ORDER BY freq DESC
            LIMIT ?
        ''', (limit,))
        
        trending = cursor.fetchall()
        conn.close()
        
        return [{"query": q[0], "frequency": q[1]} for q in trending]
        
    except Exception as e:
        print(f"Error getting trending queries: {e}")
        return []

def get_personalized_recommendations(user_id):
    """获取个性化推荐"""
    recommendations = {
        'recent_searches': [],
        'frequent_searches': [],
        'related_queries': [],
        'trending_topics': []
    }
    
    try:
        conn = sqlite3.connect(USER_DB_FILE)
        cursor = conn.cursor()
        
        # 最近搜索
        cursor.execute('''
            SELECT DISTINCT query 
            FROM user_queries 
            WHERE user_id = ? 
            ORDER BY timestamp DESC 
            LIMIT 5
        ''', (user_id,))
        recommendations['recent_searches'] = [row[0] for row in cursor.fetchall()]
        
        # 频繁搜索
        cursor.execute('''
            SELECT query, COUNT(*) as freq
            FROM user_queries 
            WHERE user_id = ? 
            GROUP BY query
            ORDER BY freq DESC
            LIMIT 5
        ''', (user_id,))
        recommendations['frequent_searches'] = [{"query": row[0], "count": row[1]} for row in cursor.fetchall()]
        
        # 相关查询（基于用户最常搜索的词）
        if recommendations['frequent_searches']:
            top_query = recommendations['frequent_searches'][0]['query']
            recommendations['related_queries'] = get_related_queries(top_query, user_id, 5)
        
        # 热门话题
        recommendations['trending_topics'] = get_trending_queries(5)
        
        conn.close()
        
    except Exception as e:
        print(f"Error getting personalized recommendations: {e}")
    
    return recommendations
# 在辅助函数部分添加用户管理功能
def init_user_db():
    """初始化用户数据库"""
    conn = sqlite3.connect(USER_DB_FILE)
    cursor = conn.cursor()
    
    # 创建用户表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT DEFAULT 'student',
            college TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # 创建用户查询历史表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_queries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            username TEXT,
            query TEXT NOT NULL,
            advanced_params TEXT,
            results_count INTEGER,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')
    
    # 创建用户点击历史表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_clicks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            username TEXT,
            url TEXT NOT NULL,
            from_query TEXT,
            result_rank INTEGER,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')
    
    conn.commit()
    conn.close()

def create_default_users():
    """创建默认用户账户"""
    conn = sqlite3.connect(USER_DB_FILE)
    cursor = conn.cursor()
    
    default_users = [
        ('2312228', '123456', 'student', '计算机学院'),
        ('2312229', '123456', 'teacher', '计算机学院'),
        ('2312230', '123456', 'student', '数学学院'),
        ('admin', 'admin123', 'admin', '管理员'),
    ]
    
    for username, password, role, college in default_users:
        password_hash = generate_password_hash(password)
        try:
            cursor.execute('''
                INSERT OR IGNORE INTO users (username, password_hash, role, college)
                VALUES (?, ?, ?, ?)
            ''', (username, password_hash, role, college))
        except sqlite3.IntegrityError:
            pass  # 用户已存在
    
    conn.commit()
    conn.close()
    print("Default users created/verified")

def authenticate_user(username, password):
    """验证用户登录"""
    conn = sqlite3.connect(USER_DB_FILE)
    cursor = conn.cursor()
    
    cursor.execute('SELECT id, password_hash, role, college FROM users WHERE username = ?', (username,))
    user = cursor.fetchone()
    conn.close()
    
    if user and check_password_hash(user[1], password):
        return {
            'id': user[0],
            'username': username,
            'role': user[2],
            'college': user[3]
        }
    return None

def register_user(username, password, role='student', college=''):
    """注册新用户"""
    conn = sqlite3.connect(USER_DB_FILE)
    cursor = conn.cursor()
    
    password_hash = generate_password_hash(password)
    
    try:
        cursor.execute('''
            INSERT INTO users (username, password_hash, role, college)
            VALUES (?, ?, ?, ?)
        ''', (username, password_hash, role, college))
        conn.commit()
        user_id = cursor.lastrowid
        conn.close()
        return user_id
    except sqlite3.IntegrityError:
        conn.close()
        return None  # 用户名已存在

def login_required(f):
    """装饰器：要求用户登录"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function
def log_user_query(user_id, username, user_query, num_results, advanced_params=None):
    """记录用户查询到数据库"""
    conn = sqlite3.connect(USER_DB_FILE)
    cursor = conn.cursor()
    
    advanced_params_str = str(advanced_params) if advanced_params else None
    
    cursor.execute('''
        INSERT INTO user_queries (user_id, username, query, advanced_params, results_count)
        VALUES (?, ?, ?, ?, ?)
    ''', (user_id, username, user_query, advanced_params_str, num_results))
    
    conn.commit()
    conn.close()
    
    # 同时记录到原有的文本日志
    log_query(f"[{username}] {user_query}", num_results, advanced_params)

def log_user_click(user_id, username, target_url, from_query='', result_rank=''):
    """记录用户点击到数据库"""
    conn = sqlite3.connect(USER_DB_FILE)
    cursor = conn.cursor()
    
    cursor.execute('''
        INSERT INTO user_clicks (user_id, username, url, from_query, result_rank)
        VALUES (?, ?, ?, ?, ?)
    ''', (user_id, username, target_url, from_query, result_rank))
    
    conn.commit()
    conn.close()
    
    # 同时记录到原有的文本日志
    log_click(target_url, f"[{username}] {from_query}", result_rank)

@app.route('/login', methods=['GET', 'POST'])
def login():
    """用户登录"""
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        user = authenticate_user(username, password)
        if user:
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['role'] = user['role']
            session['college'] = user['college']
            flash(f'欢迎，{username}！', 'success')
            return redirect(url_for('index_page'))
        else:
            flash('用户名或密码错误', 'error')
    
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    """用户注册"""
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        role = request.form.get('role', 'student')
        college = request.form.get('college', '')
        
        if len(username) < 3:
            flash('用户名至少3个字符', 'error')
        elif len(password) < 6:
            flash('密码至少6个字符', 'error')
        else:
            user_id = register_user(username, password, role, college)
            if user_id:
                flash('注册成功，请登录', 'success')
                return redirect(url_for('login'))
            else:
                flash('用户名已存在', 'error')
    
    return render_template('register.html')

@app.route('/logout')
def logout():
    """用户注销"""
    session.clear()
    flash('已成功退出', 'info')
    return redirect(url_for('index_page'))

@app.route('/profile')
@login_required
def profile():
    """用户个人中心"""
    user_id = session['user_id']
    username = session['username']
    
    # 获取用户查询历史
    conn = sqlite3.connect(USER_DB_FILE)
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT query, results_count, timestamp 
        FROM user_queries 
        WHERE user_id = ? 
        ORDER BY timestamp DESC 
        LIMIT 50
    ''', (user_id,))
    query_history = cursor.fetchall()
    
    cursor.execute('''
        SELECT url, from_query, timestamp 
        FROM user_clicks 
        WHERE user_id = ? 
        ORDER BY timestamp DESC 
        LIMIT 50
    ''', (user_id,))
    click_history = cursor.fetchall()
    
    conn.close()
    
    return render_template('profile.html', 
                         query_history=query_history,
                         click_history=click_history)






# 点击日志文件路径
CLICK_LOG_FILE = r"d:\桌面\Web-Search-Engine-main\query_service\click_log.txt"

def log_click(target_url, from_query='', result_rank=''):
    """记录用户点击行为"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_entry = f"{timestamp} - Click: {target_url}"
    if from_query:
        log_entry += f" - Query: \"{from_query}\""
    if result_rank:
        log_entry += f" - Rank: {result_rank}"
    log_entry += "\n"
    
    try:
        with open(CLICK_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(log_entry)
        print(f"Debug: Logged click to {target_url}")
    except Exception as e:
        print(f"Error writing to click log: {e}")

def get_click_statistics():
    """获取点击统计数据"""
    stats = {
        'total_clicks': 0,
        'top_domains': {},
        'recent_clicks': [],
        'top_queries': {}
    }
    
    try:
        if os.path.exists(CLICK_LOG_FILE):
            with open(CLICK_LOG_FILE, 'r', encoding='utf-8') as f:
                logs = f.readlines()
            
            stats['total_clicks'] = len(logs)
            
            # 分析域名分布
            from urllib.parse import urlparse
            for log in logs:
                if 'Click:' in log:
                    try:
                        url_part = log.split('Click: ')[1].split(' - ')[0]
                        domain = urlparse(url_part).netloc
                        stats['top_domains'][domain] = stats['top_domains'].get(domain, 0) + 1
                    except:
                        pass
            
            # 获取最近的点击
            stats['recent_clicks'] = logs[-20:][::-1]  # 最近20条，倒序
            
            # 分析热门查询
            for log in logs:
                if 'Query:' in log:
                    try:
                        query_part = log.split('Query: "')[1].split('"')[0]
                        stats['top_queries'][query_part] = stats['top_queries'].get(query_part, 0) + 1
                    except:
                        pass
            
            # 排序top domains和queries
            stats['top_domains'] = dict(sorted(stats['top_domains'].items(), 
                                             key=lambda x: x[1], reverse=True)[:10])
            stats['top_queries'] = dict(sorted(stats['top_queries'].items(), 
                                             key=lambda x: x[1], reverse=True)[:10])
    
    except Exception as e:
        print(f"Error getting click statistics: {e}")
    
    return stats




def log_query(user_query, num_results, advanced_params=None):
    """记录用户查询到日志文件"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_entry = f"{timestamp} - Query: \"{user_query}\""
    if advanced_params:
        log_entry += f" - Advanced: {advanced_params}"
    log_entry += f" - Results: {num_results}\n"
    try:
        with open(QUERY_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(log_entry)
    except Exception as e:
        print(f"Error writing to query log: {e}")

def parse_advanced_query(query_string):
    """
    改进的高级搜索指令解析，支持更复杂的语法
    """
    
    # 保存原始查询用于调试
    original_query = query_string
    
    # 初始化返回值
    main_query_parts = []
    site_filter = None
    filetype_filter = None
    filename_filter = None
    
    # 1. 提取短语查询 "xxx"
    phrase_pattern = r'"([^"]*)"'
    phrases = re.findall(phrase_pattern, query_string)
    for phrase in phrases:
        if phrase.strip():
            main_query_parts.append(f'"{phrase}"')
    
    # 移除已处理的短语
    query_without_phrases = re.sub(phrase_pattern, '', query_string)
    
    # 2. 提取高级指令
    terms = query_without_phrases.split()
    
    for term in terms:
        term = term.strip()
        if not term:
            continue
            
        if term.lower().startswith("site:"):
            site_filter = term[5:].strip()  # 去掉 "site:" 前缀
        elif term.lower().startswith("filetype:"):
            filetype_filter = term[9:].strip().lower()  # 去掉 "filetype:" 前缀
        elif term.lower().startswith("filename:"):
            filename_filter = term[9:].strip()  # 去掉 "filename:" 前缀
        else:
            # 检查是否是通配符查询
            if '*' in term:
                # 保持通配符原样，不要分割
                main_query_parts.append(term)
            else:
                # 普通查询词
                if term.strip():
                    main_query_parts.append(term)
    
    main_query_terms = " ".join(main_query_parts)
    
    print(f"Debug: Parsed '{original_query}' -> Main: '{main_query_terms}', Site: '{site_filter}', Filetype: '{filetype_filter}', Filename: '{filename_filter}'")
    
    return main_query_terms, site_filter, filetype_filter, filename_filter
# --- Flask 路由 ---
@app.route('/', methods=['GET'])
def index_page():
    return render_template('search.html')

@app.route('/search', methods=['GET'])
def search():
    if not ix:
        return "Error: Whoosh index not available.", 500

    query_str = request.args.get('q', '')
    page = int(request.args.get('page', 1))
    results_per_page = 10

    if not query_str:
        return render_template('search.html', error="Please enter a search query.")

    # 解析高级搜索指令
    main_query, site_filter, filetype_filter, filename_filter = parse_advanced_query(query_str)
    
    print(f"Debug: Parsed query - Main: '{main_query}', Site: '{site_filter}', Filetype: '{filetype_filter}', Filename: '{filename_filter}'")
    
    advanced_log_params = {}
    if site_filter: advanced_log_params['site'] = site_filter
    if filetype_filter: advanced_log_params['filetype'] = filetype_filter
    if filename_filter: advanced_log_params['filename'] = filename_filter

    with ix.searcher() as searcher:
        print(f"Debug: Available fields in index: {list(ix.schema.names())}")
        
        # 构建主查询
        final_query = None
        
        # 1. 处理主查询词
        # if main_query.strip():
        #     # 检查是否包含通配符
        #     if '*' in main_query:
        #         print(f"Debug: Detected wildcard query: {main_query}")
        #
        #
        #         wildcard_queries = []
        #         terms = main_query.split()
        #
        #         for term in terms:
        #             if '*' in term:
        #                 # 为每个字段创建通配符查询
        #                 wildcard_queries.extend([
        #                     Wildcard("title", term),
        #                     Wildcard("content", term)
        #                 ])
        #             else:
        #                 # 普通词汇，使用标准解析
        #                 parser = MultifieldParser(["title", "content"], schema=ix.schema)
        #                 try:
        #                     parsed_term = parser.parse(term)
        #                     wildcard_queries.append(parsed_term)
        #                 except:
        #                     pass
        #
        #         if wildcard_queries:
        #             final_query = Or(wildcard_queries) if len(wildcard_queries) > 1 else wildcard_queries[0]
        #             print(f"Debug: Wildcard query constructed: {final_query}")
        #
        #     else:
        #         # 普通查询，使用原有逻辑
        #         parser = MultifieldParser(["title", "content"], schema=ix.schema)
        #         parser.add_plugin(WildcardPlugin())
        #
        #         try:
        #             parsed_query = parser.parse(main_query)
        #             final_query = parsed_query
        #             print(f"Debug: Main query parsed successfully: {parsed_query}")
        #         except Exception as e:
        #             print(f"Debug: Query parsing error: {e}")
        #             return render_template('search.html', query=query_str, error=f"Query parsing error: {e}")
        # 在search()函数中，修改主查询处理部分（约第232行之后）
        # 1. 处理主查询词
        if main_query.strip():
            # 检查是否包含短语查询
            if '"' in main_query:
                print(f"Debug: Detected phrase query: {main_query}")



                phrase_queries = []

                # 提取所有短语
                phrase_pattern = r'"([^"]*)"'
                phrases = re.findall(phrase_pattern, main_query)
                remaining_terms = re.sub(phrase_pattern, '', main_query).strip().split()

                # 为每个短语创建精确匹配查询
                for phrase in phrases:
                    if phrase.strip():
                        # 方法1: 使用Term查询进行精确匹配
                        phrase_queries.extend([
                            Term("title", phrase),
                            Term("content", phrase)
                        ])

                        # 方法2: 使用正则表达式匹配（如果方法1不工作）
                        # phrase_queries.extend([
                        #     Regex("title", f".*{re.escape(phrase)}.*"),
                        #     Regex("content", f".*{re.escape(phrase)}.*")
                        # ])

                # 处理剩余的普通词汇
                if remaining_terms:
                    parser = MultifieldParser(["title", "content"], schema=ix.schema)
                    parser.add_plugin(WildcardPlugin())

                    for term in remaining_terms:
                        if term.strip():
                            try:
                                parsed_term = parser.parse(term)
                                phrase_queries.append(parsed_term)
                            except:
                                pass

                if phrase_queries:
                    final_query = Or(phrase_queries)
                    print(f"Debug: Phrase query constructed: {final_query}")

            # 检查是否包含通配符
            elif '*' in main_query:
                print(f"Debug: Detected wildcard query: {main_query}")

                wildcard_queries = []
                terms = main_query.split()

                for term in terms:
                    if '*' in term:
                        # 为每个字段创建通配符查询
                        wildcard_queries.extend([
                            Wildcard("title", term),
                            Wildcard("content", term)
                        ])
                    else:
                        # 普通词汇，使用标准解析
                        parser = MultifieldParser(["title", "content"], schema=ix.schema)
                        try:
                            parsed_term = parser.parse(term)
                            wildcard_queries.append(parsed_term)
                        except:
                            pass

                if wildcard_queries:
                    final_query = Or(wildcard_queries) if len(wildcard_queries) > 1 else wildcard_queries[0]
                    print(f"Debug: Wildcard query constructed: {final_query}")

            else:
                # 普通查询，使用原有逻辑
                parser = MultifieldParser(["title", "content"], schema=ix.schema)
                parser.add_plugin(WildcardPlugin())

                try:
                    parsed_query = parser.parse(main_query)
                    final_query = parsed_query
                    print(f"Debug: Main query parsed successfully: {parsed_query}")
                except Exception as e:
                    print(f"Debug: Query parsing error: {e}")
                    return render_template('search.html', query=query_str, error=f"Query parsing error: {e}")
        # 2. 构建过滤条件
        filter_queries = []

        # 站内查询 (site:)
        # 在search()函数中修改站内查询部分
        if site_filter:
            print(f"Debug: Applying site filter: {site_filter}")

            # 尝试多种匹配方式
            site_queries = [
                # 方法1: 精确包含匹配
                Term("url", f"*{site_filter}*"),
                # 方法2: 使用Wildcard查询
                Wildcard("url", f"*{site_filter}*"),
                # 方法3: 使用正则表达式
                Regex("url", f".*{re.escape(site_filter)}.*"),
                # 方法4: 部分URL匹配
                Term("url", f"*://{site_filter}/*"),
            ]

            # 使用OR组合多种匹配方式
            site_query = Or(site_queries)
            filter_queries.append(site_query)

            print(f"Debug: Site query: {site_query}")
        

        # 文档类型查询 (filetype:)
        if filetype_filter:
            print(f"Debug: Applying filetype filter: {filetype_filter}")
            # 检查索引中是否有filetype字段
            if "filetype" in ix.schema:
                filter_queries.append(Term("filetype", filetype_filter))
            else:
                # 如果没有专门的filetype字段，从URL或filename中推断
                filetype_query = Or([
                    Term("url", f"*.{filetype_filter}"),
                    Term("filename", f"*.{filetype_filter}") if "filename" in ix.schema else None
                ])
                if filetype_query:
                    filter_queries.append(filetype_query)

        # 文件名查询 (filename:)
        if filename_filter:
            print(f"Debug: Applying filename filter: {filename_filter}")
            if "filename" in ix.schema:
                # 支持部分匹配
                filename_query = Term("filename", f"*{filename_filter}*")
                filter_queries.append(filename_query)
            else:
                # 如果没有filename字段，在title中搜索
                filename_query = Term("title", f"*{filename_filter}*")
                filter_queries.append(filename_query)
        
        # 3. 组合查询
        if filter_queries:
            if final_query:
                # 主查询 + 过滤条件
                final_query = And([final_query] + filter_queries)
            else:
                # 只有过滤条件
                final_query = And(filter_queries)
                
        print(f"Debug: Final query: {final_query}")

        if not final_query:
            return render_template('results.html', query=query_str, results_page=None, total_results=0, error="No valid query terms provided.")

        # 4. 执行搜索
        try:
            # 获取总结果数
            all_results = searcher.search(final_query, limit=None)
            total_results = len(all_results)
            
            print(f"Debug: Found {total_results} total results")
            
            # 分页获取结果
            results_page = searcher.search_page(final_query, page, pagelen=results_per_page)
            
            # 设置高亮显示
            if hasattr(results_page.results, 'fragmenter'):
                results_page.results.fragmenter.surround = 100

        except Exception as e:
            print(f"Debug: Search execution error: {e}")
            import traceback
            traceback.print_exc()
            return render_template('results.html', query=query_str, results_page=None, total_results=0, error=f"Search execution error: {e}")

        # 5. 记录查询日志
        if 'user_id' in session:
            log_user_query(session['user_id'], session['username'], query_str, total_results,
                           advanced_log_params if advanced_log_params else None)
        else:
            log_query(f"[Anonymous] {query_str}", total_results, advanced_log_params if advanced_log_params else None)
        # 6. 处理搜索结果
        processed_results = []
        try:
            for i, hit in enumerate(results_page):
                print(f"Debug: Processing hit with fields: {list(hit.keys())}")

                # 安全获取字段值
                publish_date_obj = hit.get("date") or hit.get("publish_date")
                id_val = hit.get("id")
                id_in_index_str = str(id_val) if id_val is not None else None

                # 获取原始URL
                original_url = hit.get("url", "#")

                # 构建跳转服务URL
                if original_url != "#":
                    encoded_url = quote(original_url, safe='')
                    redirect_url = f"/redirect/{encoded_url}?from_query={quote(query_str)}&result_rank={i + 1}"
                else:
                    redirect_url = "#"

                res_item = {
                    "title": hit.get("title", "No Title"),
                    "url": redirect_url,  # 使用跳转服务URL
                    "original_url": original_url,  # 保留原始URL用于显示
                    "score": hit.score,
                    "publish_date": publish_date_obj,
                    "source": hit.get("source", "Unknown"),
                    "filetype": hit.get("filetype", ""),
                    "filename": hit.get("filename", ""),
                    "highlight": "",
                    "id_in_index": id_in_index_str,
                    "original_data_source_dir": hit.get("original_data_source_dir", DEFAULT_NEWS_CRAWL_SUBDIR)
                }
                # 生成高亮摘要
                try:
                    if hit.highlights("content"):
                        res_item["highlight"] = hit.highlights("content", top=2)
                    elif hit.highlights("title"):
                        res_item["highlight"] = hit.highlights("title", top=1)
                    else:
                        # 生成简单摘要
                        content = hit.get("content", "")
                        if content:
                            res_item["highlight"] = content[:200] + "..." if len(content) > 200 else content
                except Exception as highlight_error:
                    print(f"Debug: Highlight error: {highlight_error}")
                    content = hit.get("content", "")
                    res_item["highlight"] = content[:200] + "..." if len(content) > 200 else content
                
                processed_results.append(res_item)
                
        except Exception as e_proc:
            print(f"!!! Critical error processing results: {e_proc} !!!")
            import traceback
            traceback.print_exc()
            return f"Server Error: Problem processing search results. Details: {e_proc}", 500

        try:
            return render_template('results.html', 
                                   query=query_str, 
                                   results_page=results_page, 
                                   processed_results=processed_results,
                                   total_results=total_results,
                                   page=page,
                                   results_per_page=results_per_page)
        except Exception as e_render:
            print(f"!!! Critical error rendering template: {e_render} !!!")
            import traceback
            traceback.print_exc()
            return f"Server Error: Problem displaying search results. Details: {e_render}", 500
        

@app.route('/snapshot/<original_data_source_dir>/<news_id_in_index>')
def snapshot(original_data_source_dir, news_id_in_index):
    """
    显示新闻快照。
    original_data_source_dir: 如 "nankai_news_2025_05_29_00_39_58"
    news_id_in_index: 新闻在索引中的ID，可能格式如 "1387_dup_6610"
    """
    if not original_data_source_dir or not news_id_in_index:
        abort(400, "Missing snapshot identification parameters.")

    try:
        # 处理特殊的ID格式 - 从 "1387_dup_6610" 中提取基础数字 "1387"
        actual_news_id = news_id_in_index
        
        # 如果ID包含 "_dup_"，提取前面的数字部分
        if '_dup_' in news_id_in_index:
            actual_news_id = news_id_in_index.split('_dup_')[0]
        # 如果ID包含其他下划线格式，提取第一个数字部分
        elif '_' in news_id_in_index:
            parts = news_id_in_index.split('_')
            if parts[0].isdigit():
                actual_news_id = parts[0]
        
        print(f"Debug: Original ID: {news_id_in_index}, Extracted ID: {actual_news_id}")

        # 1. 定位并读取 news_X.json 文件
        news_json_filename = f"news_{actual_news_id}.json"
        news_json_path = os.path.join(NEWS_DATA_BASE_DIR, original_data_source_dir, "news", news_json_filename)

        print(f"Debug: Looking for news file: {news_json_path}")

        if not os.path.exists(news_json_path):
            news_dir = os.path.join(NEWS_DATA_BASE_DIR, original_data_source_dir, "news")
            debug_info = f"News file not found: {news_json_path}\n"
            debug_info += f"Original ID: {news_id_in_index}, Extracted ID: {actual_news_id}\n"
            
            if os.path.exists(news_dir):
                try:
                    sample_files = [f for f in os.listdir(news_dir) if f.endswith('.json')][:10]
                    debug_info += f"Sample files in news directory: {sample_files}"
                except Exception as e:
                    debug_info += f"Error listing news directory: {e}"
            else:
                debug_info += f"News directory does not exist: {news_dir}"
            
            print(debug_info)
            abort(404, f"News metadata file not found: {news_json_path}\n{debug_info}")

        # 读取新闻文件并检查其结构
        with open(news_json_path, 'r', encoding='utf-8') as f:
            news_data = json.load(f)
        
        print(f"Debug: News file structure: {list(news_data.keys())}")  # 显示新闻文件中的所有字段
        
        # 尝试多种可能的快照ID字段名
        snapshot_id_ref = None
        possible_snapshot_fields = ['snapshot_id', 'id', 'snapshot_ref', 'snapshot', 'snap_id']
        
        for field in possible_snapshot_fields:
            if field in news_data and news_data[field] is not None:
                snapshot_id_ref = news_data[field]
                print(f"Debug: Found snapshot reference in field '{field}': {snapshot_id_ref}")
                break
        
        # 如果没有找到快照ID，尝试使用新闻ID本身作为快照ID
        if snapshot_id_ref is None:
            print(f"Debug: No snapshot_id field found, trying to use news ID ({actual_news_id}) as snapshot ID")
            snapshot_id_ref = actual_news_id
        
        print(f"Debug: Using snapshot_id: {snapshot_id_ref}")

        # 2. 尝试多种可能的快照文件命名格式
        possible_snapshot_filenames = [
            f"snapshot_{snapshot_id_ref}.json",
            f"{snapshot_id_ref}.json",
            f"snap_{snapshot_id_ref}.json",
        ]
        
        snapshots_dir = os.path.join(NEWS_DATA_BASE_DIR, original_data_source_dir, "snapshots")
        snapshot_json_path = None
        snapshot_json_filename = None
        
        for filename in possible_snapshot_filenames:
            test_path = os.path.join(snapshots_dir, filename)
            print(f"Debug: Trying snapshot file: {test_path}")
            if os.path.exists(test_path):
                snapshot_json_path = test_path
                snapshot_json_filename = filename
                break
        
        if not snapshot_json_path:
            # 提供详细的快照调试信息
            debug_info = f"Snapshot file not found for snapshot_id: {snapshot_id_ref}\n"
            debug_info += f"Tried filenames: {possible_snapshot_filenames}\n"
            debug_info += f"In directory: {snapshots_dir}\n"
            
            if os.path.exists(snapshots_dir):
                try:
                    actual_snapshots = [f for f in os.listdir(snapshots_dir) if f.endswith('.json')]
                    actual_snapshots.sort()
                    sample_snapshots = actual_snapshots[:20]
                    debug_info += f"Sample snapshot files: {sample_snapshots}\n"
                    debug_info += f"Total snapshot files: {len(actual_snapshots)}\n"
                    
                    # 智能匹配：查找包含相似ID的快照文件
                    matching_snapshots = [f for f in actual_snapshots if str(snapshot_id_ref) in f]
                    if matching_snapshots:
                        debug_info += f"Files containing snapshot ID '{snapshot_id_ref}': {matching_snapshots}"
                        
                except Exception as e:
                    debug_info += f"Error listing snapshots directory: {e}"
            else:
                debug_info += f"Snapshots directory does not exist: {snapshots_dir}"
            
            print(debug_info)
            abort(404, f"Snapshot file not found. Debug info:\n{debug_info}")

        # 读取快照数据
        print(f"Debug: Successfully found snapshot file: {snapshot_json_path}")
        with open(snapshot_json_path, 'r', encoding='utf-8') as f:
            snapshot_data = json.load(f)
        
        print(f"Debug: Snapshot file structure: {list(snapshot_data.keys())}")  # 显示快照文件中的所有字段
            
        html_content = snapshot_data.get("html_content", snapshot_data.get("content", "Snapshot content not available."))
        snapshot_url = snapshot_data.get("url", news_data.get("url", "#"))
        
        print(f"Debug: Successfully loaded snapshot for news {actual_news_id}")
        
        return render_template('snapshot.html', html_content=html_content, original_url=snapshot_url)

    except FileNotFoundError as e:
        print(f"FileNotFoundError in snapshot route: {e}")
        abort(404, f"Snapshot or related metadata file not found: {str(e)}")
    except json.JSONDecodeError as e:
        print(f"JSONDecodeError in snapshot route: {e}")
        abort(500, f"Error decoding snapshot or metadata JSON: {str(e)}")
    except Exception as e:
        print(f"Unexpected error retrieving snapshot: {e}")
        import traceback
        traceback.print_exc()
        abort(500, f"An error occurred while retrieving the snapshot: {str(e)}")


@app.route('/demo')
def demo():
    """功能演示页面"""
    demo_examples = {
        "基础搜索": [
            "南开大学",
            "人工智能",
            "计算机科学"
        ],
        "站内查询": [
            "活动 site:news.nankai.edu.cn",
            "招聘 site:job.nankai.edu.cn",
            "通知 site:nankai.edu.cn"
        ],
        "文档查询": [
            "章程 filetype:pdf",
            "课程 filetype:doc",
            "规定 filetype:txt"
        ],
        "文件名查询": [
            "章程 filename:章程",
            "通知 filename:通知",
            "规定 filename:规定"
        ],
        "短语查询": [
            '"开学典礼"',
            '"校园招聘"',
            '"人工智能技术"'
        ],
        "通配查询": [
            "计算*",
            "*学习",
            "数据*分析"
        ],
        "组合查询": [
            '"校园招聘" site:job.nankai.edu.cn filetype:doc',
            '"开学典礼" site:news.nankai.edu.cn',
            '通知 site:nankai.edu.cn filetype:pdf'
        ]
    }
    return render_template('demo.html', examples=demo_examples)

@app.route('/logs')
def view_logs():
    """查看查询日志"""
    try:
        if os.path.exists(QUERY_LOG_FILE):
            with open(QUERY_LOG_FILE, 'r', encoding='utf-8') as f:
                logs = f.readlines()
            # 显示最近50条日志，倒序排列
            recent_logs = logs[-50:][::-1]
            return render_template('logs.html', logs=recent_logs)
        else:
            return render_template('logs.html', logs=[], message="No query logs found.")
    except Exception as e:
        return f"Error reading logs: {e}"


@app.route('/redirect/<path:target_url>')
def redirect_service(target_url):
    """
    跳转服务 - 记录用户点击并重定向到目标URL
    """
    from flask import redirect
    from urllib.parse import unquote
    
    try:
        # URL解码
        decoded_url = unquote(target_url)
        
        # 验证URL格式
        if not (decoded_url.startswith('http://') or decoded_url.startswith('https://')):
            decoded_url = 'http://' + decoded_url
        
        # 记录点击日志
        if 'user_id' in session:
            log_user_click(session['user_id'], session['username'], decoded_url, request.args.get('from_query', ''), request.args.get('result_rank', ''))
        else:
             log_click(decoded_url, f"[Anonymous] {request.args.get('from_query', '')}", request.args.get('result_rank', ''))
        print(f"Debug: Redirecting to: {decoded_url}")
        
        # 重定向到目标URL
        return redirect(decoded_url)
        
    except Exception as e:
        print(f"Redirect error: {e}")
        # 如果重定向失败，显示错误页面
        return render_template('redirect_error.html', 
                             target_url=target_url, 
                             error=str(e)), 400

@app.route('/click-stats')
def click_stats():
    """查看点击统计"""
    try:
        stats = get_click_statistics()
        return render_template('click_stats.html', stats=stats)
    except Exception as e:
        return f"Error loading click statistics: {e}"

@app.route('/api/search-suggestions')
def search_suggestions_api():
    """搜索建议API"""
    query = request.args.get('q', '').strip()
    if not query or len(query) < 2:
        return {"suggestions": []}
    
    user_id = session.get('user_id')
    suggestions = get_search_suggestions(query, user_id, 8)
    
    return {"suggestions": suggestions}

@app.route('/api/related-queries/<query>')
def related_queries_api(query):
    """相关查询API"""
    user_id = session.get('user_id')
    related = get_related_queries(query, user_id, 5)
    
    return {"related_queries": related}

@app.route('/recommendations')
@login_required
def recommendations():
    """个性化推荐页面"""
    user_id = session['user_id']
    recommendations = get_personalized_recommendations(user_id)
    
    return render_template('recommendations.html', recommendations=recommendations)
@app.route('/api/personalized-recommendations')
@login_required
def personalized_recommendations_api():
    """个性化推荐API"""
    user_id = session['user_id']
    recommendations = get_personalized_recommendations(user_id)
    return recommendations

@app.route('/api/trending-queries')
def trending_queries_api():
    """热门查询API"""
    trending = get_trending_queries(10)
    return trending

if __name__ == '__main__':
    # 初始化用户数据库
    init_user_db()
    create_default_users()

    # 确保 templates 文件夹存在
    if not os.path.exists(os.path.join(os.path.dirname(__file__), "templates")):
        os.makedirs(os.path.join(os.path.dirname(__file__), "templates"))
        print("Created 'templates' directory. Please add template files there.")

    app.run(debug=True, port=5001)