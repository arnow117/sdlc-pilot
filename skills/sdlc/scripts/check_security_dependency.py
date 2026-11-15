#!/usr/bin/env python3
"""Find local Codex Security CLI candidates without launching them."""

import json
import shutil
import sys


INSTALL_URL = "https://github.com/openai/codex-security#quick-start"


def inspect_environment():
    long_name = shutil.which("codex-security")
    short_name = shutil.which("cs")

    if long_name:
        state = "long_name_found"
        recommendation = (
            "发现 Codex Security 长命令候选；版本、认证和实际运行能力尚未检查。"
            "使用前请核实所需认证和运行依赖。"
        )
    elif short_name:
        state = "short_name_ambiguous"
        recommendation = (
            "发现 cs 候选，但该名称可能属于其他工具；请核实其身份。"
            "如果没有可用的 Codex Security，可按官方说明安装并配置。"
        )
    else:
        state = "not_found"
        recommendation = (
            "未发现 Codex Security CLI；如果当前宿主也没有可用插件，"
            "需要时可按官方说明安装并配置认证。"
        )

    return {
        "cli": {
            "state": state,
            "long_name": long_name,
            "short_name": short_name,
        },
        "prerequisites": {
            "node_on_path": shutil.which("node") is not None,
            "npm_on_path": shutil.which("npm") is not None,
            "python_version": ".".join(str(part) for part in sys.version_info[:3]),
        },
        "plugin": "not_checked",
        "version": "not_checked",
        "authentication": "not_checked",
        "scan": "not_run",
        "install_url": INSTALL_URL,
        "recommendation": recommendation,
    }


def main():
    print(json.dumps(inspect_environment(), ensure_ascii=True, sort_keys=True))


if __name__ == "__main__":
    main()
