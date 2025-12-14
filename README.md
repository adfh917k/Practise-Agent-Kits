
# 自动根据主题从arxiv爬取论文并分析，随后发布到小红书平台上
# 郭浩宇 李泽祥 刘一澎

# 1. 克隆或创建项目
mkdir paper_reading_agent
cd paper_reading_agent

# 2. 安装依赖
pip install mcp arxiv PyPDF2 anthropic python-dotenv zhipuai chromadb Pillow

# 3. 配置 API Key
config 设置 
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
运行需在文件夹下创建文件.env，并指定ANTHROPIC_API_KEY来运行


# 5. 运行
python agent.py

### 注意! 请不要使用print, 
采用def log(msg):  
    print(msg, file=sys.stderr, flush=True)
然后:
    log(".....")
的方式来打印