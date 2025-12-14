import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

ZHIPU_API_KEY = os.getenv("ZHIPU_API_KEY")

# 项目路径
PROJECT_ROOT = Path(__file__).parent
CACHE_DIR = PROJECT_ROOT / "cache"
CACHE_DIR.mkdir(exist_ok=True)

# API Keys
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
USE_LOCAL_MODELS = None

# 小红书配置（Demo 用模拟数据）
XIAOHONGSHU_USERNAME = os.getenv("XHS_USERNAME", "demo_user")
XIAOHONGSHU_PASSWORD = os.getenv("XHS_PASSWORD", "demo_pass")

# MCP Server 配置
MCP_SERVERS = {
    "crawler": {
        "command": "python",
        "args": ["mcp_servers/arxiv_crawler_server.py"]
    },
    "processor": {
        "command": "python",
        "args": ["mcp_servers/paper_processor_server.py"]
    },
    "publisher": {
        "command": "python",
        "args": ["mcp_servers/xiaohongshu_publisher_server.py"]
    }
}