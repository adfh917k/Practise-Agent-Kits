#!/usr/bin/env python3
"""
MCP Server 1: Arxiv 论文爬取服务
功能：
- 搜索论文
- 下载 PDF
- 提取基本信息
"""

import asyncio
import json
import sys
from pathlib import Path
from typing import Any

import arxiv
import requests
from mcp.server import Server
from mcp.types import Tool, TextContent
from mcp.server.stdio import stdio_server

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))
from config import CACHE_DIR

app = Server("arxiv-crawler")


@app.list_tools()
async def list_tools() -> list[Tool]:
    """列出可用工具"""
    return [
        Tool(
            name="search_papers",
            description="在 Arxiv 上搜索论文，返回论文列表",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "搜索关键词，例如 'transformer', 'attention mechanism'"
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "最大返回结果数",
                        "default": 5
                    },
                    "sort_by": {
                        "type": "string",
                        "enum": ["relevance", "lastUpdatedDate", "submittedDate"],
                        "default": "relevance",
                        "description": "排序方式"
                    }
                },
                "required": ["query"]
            }
        ),
        Tool(
            name="download_paper",
            description="下载论文 PDF 到本地",
            inputSchema={
                "type": "object",
                "properties": {
                    "paper_id": {
                        "type": "string",
                        "description": "论文的 arxiv ID，例如 '2301.12345'"
                    },
                    "pdf_url": {
                        "type": "string",
                        "description": "PDF 下载链接"
                    }
                },
                "required": ["paper_id", "pdf_url"]
            }
        ),
        Tool(
            name="get_paper_metadata",
            description="获取论文的详细元数据",
            inputSchema={
                "type": "object",
                "properties": {
                    "paper_id": {
                        "type": "string",
                        "description": "论文的 arxiv ID"
                    }
                },
                "required": ["paper_id"]
            }
        )
    ]


@app.call_tool()
async def call_tool(name: str, arguments: Any) -> list[TextContent]:
    """处理工具调用"""
    
    if name == "search_papers":
        return await search_papers(
            query=arguments["query"],
            max_results=arguments.get("max_results", 5),
            sort_by=arguments.get("sort_by", "relevance")
        )
    
    elif name == "download_paper":
        return await download_paper(
            paper_id=arguments["paper_id"],
            pdf_url=arguments["pdf_url"]
        )
    
    elif name == "get_paper_metadata":
        return await get_paper_metadata(
            paper_id=arguments["paper_id"]
        )
    
    else:
        raise ValueError(f"Unknown tool: {name}")

def log(msg):
    print(msg, file=sys.stderr, flush=True)


def _do_search(search) -> list:
    """在线程中执行阻塞的搜索操作"""

    client = arxiv.Client(
        page_size=10,
        delay_seconds=3.0,  # 每次请求后暂停3秒，防止被封 IP
        num_retries=3       # 库内部自动重试
    )
    results = []
    for result in client.results(search):
        results.append({
            "paper_id": result.entry_id.split('/')[-1],
            "title": result.title,
            "authors": [author.name for author in result.authors],
            "abstract": result.summary,
            "published": result.published.isoformat(),
            "updated": result.updated.isoformat(),
            "pdf_url": result.pdf_url,
            "categories": result.categories,
            "primary_category": result.primary_category
        })
    return results


async def search_papers(query: str, max_results: int, sort_by: str) -> list[TextContent]:
    """搜索 Arxiv 论文"""
    try:
        # 映射排序方式
        sort_map = {
            "relevance": arxiv.SortCriterion.Relevance,
            "lastUpdatedDate": arxiv.SortCriterion.LastUpdatedDate,
            "submittedDate": arxiv.SortCriterion.SubmittedDate
        }

        # search = arxiv.Search(
        #     query=query,
        #     max_results=max_results,
        #     sort_by=sort_map.get(sort_by, arxiv.SortCriterion.Relevance),
        # )

        # client = arxiv.Client(
        # page_size=10,
        # delay_seconds=3.0,  # 每次请求后暂停3秒，防止被封 IP
        # num_retries=3       # 库内部自动重试
        # )
        
        search = arxiv.Search(
            query=query,
            max_results=max_results,
            sort_by=sort_map.get(sort_by, arxiv.SortCriterion.Relevance),
        )

        timeout = 5  # 30 秒超时
        max_retries = 5
        papers = []
        last_error = None

        for attempt in range(1, max_retries + 1):
            log(f"📚 搜索 Arxiv 论文 (第 {attempt} 次尝试)...")
            try:
                # 在线程池中执行阻塞操作，并设置超时
                loop = asyncio.get_event_loop()
                papers = await asyncio.wait_for(
                    loop.run_in_executor(None, _do_search, search),
                    timeout=timeout
                )
                log(f"✅ 搜索成功，获取到 {len(papers)} 篇论文")
                break
            except asyncio.TimeoutError:
                last_error = f"第 {attempt} 次尝试超时"
                log(f"⚠️ {last_error}")
            except Exception as e:
                last_error = str(e)
                log(f"⚠️ 第 {attempt} 次尝试失败: {last_error}")
        else:
            # 所有尝试都失败
            raise Exception(f"Arxiv 搜索失败（已重试 {max_retries} 次）: {last_error}")

        result_text = json.dumps({
            "success": True,
            "count": len(papers),
            "papers": papers
        }, indent=2, ensure_ascii=False)

        return [TextContent(type="text", text=result_text)]

    except Exception as e:
        error_text = json.dumps({
            "success": False,
            "error": str(e)
        })
        return [TextContent(type="text", text=error_text)]


async def download_paper(paper_id: str, pdf_url: str) -> list[TextContent]:
    """下载论文 PDF"""
    try:
        # 清理 paper_id（移除版本号）
        clean_id = paper_id.split('v')[0]
        
        # 本地保存路径
        pdf_path = CACHE_DIR / f"{clean_id}.pdf"
        
        # 如果已存在，直接返回
        if pdf_path.exists():
            result_text = json.dumps({
                "success": True,
                "message": "PDF already exists",
                "path": str(pdf_path),
                "paper_id": clean_id
            })
            return [TextContent(type="text", text=result_text)]
        
        # 下载 PDF
        response = requests.get(pdf_url, timeout=30)
        response.raise_for_status()
        
        # 保存文件
        with open(pdf_path, 'wb') as f:
            f.write(response.content)
        
        result_text = json.dumps({
            "success": True,
            "message": "PDF downloaded successfully",
            "path": str(pdf_path),
            "paper_id": clean_id,
            "size_mb": round(len(response.content) / 1024 / 1024, 2)
        })
        
        return [TextContent(type="text", text=result_text)]
    
    except Exception as e:
        error_text = json.dumps({
            "success": False,
            "error": str(e)
        })
        return [TextContent(type="text", text=error_text)]


async def get_paper_metadata(paper_id: str) -> list[TextContent]:
    """获取论文详细信息"""
    try:
        search = arxiv.Search(id_list=[paper_id])
        result = next(search.results())
        
        metadata = {
            "paper_id": paper_id,
            "title": result.title,
            "authors": [author.name for author in result.authors],
            "abstract": result.summary,
            "published": result.published.isoformat(),
            "updated": result.updated.isoformat(),
            "pdf_url": result.pdf_url,
            "categories": result.categories,
            "primary_category": result.primary_category,
            "comment": result.comment,
            "journal_ref": result.journal_ref,
            "doi": result.doi
        }
        
        result_text = json.dumps({
            "success": True,
            "metadata": metadata
        }, indent=2, ensure_ascii=False)
        
        return [TextContent(type="text", text=result_text)]
    
    except Exception as e:
        error_text = json.dumps({
            "success": False,
            "error": str(e)
        })
        return [TextContent(type="text", text=error_text)]


if __name__ == "__main__":
    import asyncio
    import mcp.server.stdio
    
    async def main():
        async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
            await app.run(
                read_stream,
                write_stream,
                app.create_initialization_options()
            )
    
    asyncio.run(main())