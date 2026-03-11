#!/usr/bin/env python3
"""
CLI 入口 —— 命令行方式运行合规审核
支持：
  - 审核单个文件
  - 启动 API 服务
  - 审核示例文本
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path

# 确保项目根目录在 sys.path 中
ROOT_DIR = Path(__file__).parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

# 将 src 加入搜索路径，支持 `from moderation import ...`
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from moderation import config
from moderation.log import setup_logging
from moderation.workflow import run_audit, run_audit_sync


def cmd_audit(args):
    """执行审核"""
    # 读取输入文本
    if args.file:
        file_path = Path(args.file)
        if not file_path.exists():
            print(f"错误: 文件不存在 - {file_path}")
            sys.exit(1)
        input_text = file_path.read_text(encoding="utf-8")
        print(f"已加载文件: {file_path} ({len(input_text)} 字)")
    elif args.text:
        input_text = args.text
    else:
        # 使用示例文本
        sample_path = ROOT_DIR / "data" / "sample_input.txt"
        if sample_path.exists():
            input_text = sample_path.read_text(encoding="utf-8")
            print(f"使用示例文本 ({len(input_text)} 字)")
        else:
            print("错误: 请通过 --file 或 --text 提供待审核文本")
            sys.exit(1)

    print("=" * 60)
    print("保险文本合规审核系统")
    print(f"模型: {config.LLM_MODEL}")
    print(f"API: {config.LLM_API_BASE}")
    print("=" * 60)

    # 执行审核
    response = run_audit_sync(input_text, doc_id=args.doc_id)

    # 输出结果
    result_json = response.model_dump_json(indent=2, ensure_ascii=False)

    if args.output:
        output_path = Path(args.output)
        output_path.write_text(result_json, encoding="utf-8")
        print(f"\n结果已保存到: {output_path}")
    else:
        print("\n" + "=" * 60)
        print("审核结果")
        print("=" * 60)
        print(result_json)

    # 简要摘要
    print("\n" + "-" * 60)
    print(f"文档ID: {response.doc_id}")
    print(f"违规总数: {response.total_violations}")
    print(f"处理耗时: {response.processing_time_seconds} 秒")

    if response.violations:
        print("\n违规摘要:")
        for i, v in enumerate(response.violations, 1):
            print(f"  {i}. [{v.risk_level}] {v.rule_name} ({v.rule_id})")
            for loc in v.locations:
                text_preview = loc.original_text_slice[:80]
                if len(loc.original_text_slice) > 80:
                    text_preview += "..."
                print(f"     位置 [{loc.raw_start}-{loc.raw_end}]: \"{text_preview}\"")
            print(f"     建议: {v.suggestion[:80]}...")
    else:
        print("\n✓ 未发现违规内容")


def cmd_serve(args):
    """启动 API 服务"""
    import uvicorn

    host = args.host or config.API_HOST
    port = args.port or config.API_PORT

    print("=" * 60)
    print("保险文本合规审核系统 - API 服务")
    print(f"地址: http://{host}:{port}")
    print(f"文档: http://{host}:{port}/docs")
    print("=" * 60)

    uvicorn.run(
        "moderation.api:app",
        host=host,
        port=port,
        reload=args.reload,
        log_level="info",
    )


def cmd_workflow(args):
    """通过同步方式运行审核（带详细日志输出）"""
    # 读取输入文本
    if args.file:
        file_path = Path(args.file)
        if not file_path.exists():
            print(f"错误: 文件不存在 - {file_path}")
            sys.exit(1)
        input_text = file_path.read_text(encoding="utf-8")
    else:
        sample_path = ROOT_DIR / "data" / "sample_input.txt"
        input_text = sample_path.read_text(encoding="utf-8")

    print("=" * 60)
    print("保险文本合规审核系统 (Workflow 模式)")
    print("=" * 60)

    response = run_audit_sync(input_text, doc_id=args.doc_id)
    print(response.model_dump_json(indent=2, ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser(
        description="保险文本合规审核系统",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:
  # 使用示例文本进行审核
  python run.py audit

  # 审核指定文件
  python run.py audit --file path/to/insurance_text.txt

  # 保存结果到文件
  python run.py audit --file input.txt --output result.json

  # 启动 API 服务
  python run.py serve

  # 通过 Agno Workflow 模式运行（详细 Step 输出）
  python run.py workflow
""",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="详细日志输出")
    parser.add_argument("--log-file", help="日志文件路径（默认：logs/audit.log）")

    subparsers = parser.add_subparsers(dest="command", help="子命令")

    # audit 子命令
    audit_parser = subparsers.add_parser("audit", help="执行文本合规审核")
    audit_parser.add_argument("--file", "-f", help="待审核文本文件路径")
    audit_parser.add_argument("--text", "-t", help="直接输入待审核文本")
    audit_parser.add_argument("--doc-id", help="文档ID")
    audit_parser.add_argument("--output", "-o", help="结果输出文件路径 (JSON)")
    audit_parser.set_defaults(func=cmd_audit)

    # serve 子命令
    serve_parser = subparsers.add_parser("serve", help="启动 API 服务")
    serve_parser.add_argument("--host", default=None, help=f"监听地址 (默认: {config.API_HOST})")
    serve_parser.add_argument("--port", type=int, default=None, help=f"监听端口 (默认: {config.API_PORT})")
    serve_parser.add_argument("--reload", action="store_true", help="开启热重载")
    serve_parser.set_defaults(func=cmd_serve)

    # workflow 子命令
    wf_parser = subparsers.add_parser("workflow", help="以 Agno Workflow 模式运行")
    wf_parser.add_argument("--file", "-f", help="待审核文本文件路径")
    wf_parser.add_argument("--doc-id", help="文档ID")
    wf_parser.set_defaults(func=cmd_workflow)

    args = parser.parse_args()

    # 配置日志（默认输出到文件）
    log_file = args.log_file if hasattr(args, 'log_file') and args.log_file else "logs/audit.log"
    setup_logging(verbose=args.verbose, log_file=log_file)

    if args.command is None:
        parser.print_help()
        sys.exit(0)

    args.func(args)


if __name__ == "__main__":
    main()
