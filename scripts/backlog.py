#!/usr/bin/env python3
"""sdlc-backlog 派生操作 — readyqueue / coverage / lint.

读 <root>/<domain>/<subdomain>/<leaf>.md 的 frontmatter(事实源),机械派生:
  readyqueue : 解依赖的就绪叶(A/B 契约),JSON 到 stdout
  coverage   : 按 domain 的 status 计数 burndown,JSON 到 stdout
  lint       : 断依赖 / 重复 old_system_ref / 缺字段 / 孤儿;有问题则非 0 退出

纯标准库,无第三方依赖(可移植:Claude / Codex 都能跑)。
事实源 = 叶 frontmatter;本脚本只读不写树。
"""
import argparse
import json
import os
import sys

REQUIRED_FIELDS = [
    "id", "title", "domain_path", "cross_link", "old_system_ref",
    "new_domain_path", "status", "priority", "depends_on", "risk_level",
]
PRIORITY_ORDER = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}
SHIPPED = "shipped"


def parse_frontmatter(text):
    """解析叶文件首块 --- frontmatter。只认 `key: scalar` 与内联 list `key: [a, b]`/`[]`。"""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    fm = {}
    for line in lines[1:]:
        if line.strip() == "---":
            break
        if ":" not in line:
            continue
        key, _, val = line.partition(":")
        key, val = key.strip(), val.strip()
        if val.startswith("[") and val.endswith("]"):
            inner = val[1:-1].strip()
            fm[key] = [x.strip() for x in inner.split(",") if x.strip()] if inner else []
        else:
            fm[key] = val
    return fm


def load_leaves(root):
    """返回叶 list:每个 = {fields..., _path, _depth(相对 root 的目录层数)}。跳过 _ 前缀与 _index。"""
    leaves = []
    for dirpath, _dirs, files in os.walk(root):
        for fn in files:
            if not fn.endswith(".md") or fn.startswith("_"):
                continue
            full = os.path.join(dirpath, fn)
            with open(full, encoding="utf-8") as f:
                fm = parse_frontmatter(f.read())
            rel = os.path.relpath(full, root)
            fm["_path"] = rel
            fm["_depth"] = len(os.path.dirname(rel).split(os.sep)) if os.path.dirname(rel) else 0
            leaves.append(fm)
    return leaves


def cmd_readyqueue(root):
    leaves = load_leaves(root)
    by_id = {lf.get("id"): lf for lf in leaves}
    ready = []
    for lf in leaves:
        if lf.get("status") == SHIPPED:
            continue  # 已完成,不再入队
        deps = lf.get("depends_on") or []
        if all(by_id.get(d, {}).get("status") == SHIPPED for d in deps):
            ready.append(lf)
    ready.sort(key=lambda lf: (PRIORITY_ORDER.get(lf.get("priority"), 99), lf.get("id", "")))
    out = [{
        "leaf_id": lf.get("id"),
        "title": lf.get("title"),
        "priority": lf.get("priority"),
        "deps_resolved": True,
        "old_system_ref": lf.get("old_system_ref"),
        "risk_level": lf.get("risk_level"),
        "status": lf.get("status"),
    } for lf in ready]
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


def cmd_coverage(root):
    leaves = load_leaves(root)
    cov = {}
    for lf in leaves:
        domain = (lf.get("domain_path") or lf["_path"]).split("/")[0]
        d = cov.setdefault(domain, {"total": 0, "by_status": {}})
        d["total"] += 1
        st = lf.get("status", "unknown")
        d["by_status"][st] = d["by_status"].get(st, 0) + 1
    print(json.dumps(cov, ensure_ascii=False, indent=2))
    return 0


def cmd_lint(root):
    leaves = load_leaves(root)
    by_id = {lf.get("id"): lf for lf in leaves}
    problems = []
    seen_ref = {}
    for lf in leaves:
        lid = lf.get("id", lf["_path"])
        # 缺字段
        for fld in REQUIRED_FIELDS:
            if fld not in lf:
                problems.append(f"missing-field: {lid} 缺字段 '{fld}'")
        # 断依赖
        for d in (lf.get("depends_on") or []):
            if d not in by_id:
                problems.append(f"dangling-dep: {lid} 的 depends_on 指向不存在的 '{d}'")
        # 孤儿:叶不在 <domain>/<subdomain>/ 形态(目录深度 < 2)
        if lf["_depth"] < 2:
            problems.append(f"orphan: {lid} 路径深度不足(应在 <domain>/<subdomain>/ 下)")
        # 重复 old_system_ref
        ref = lf.get("old_system_ref")
        if ref:
            seen_ref.setdefault(ref, []).append(lid)
    for ref, ids in seen_ref.items():
        if len(ids) > 1:
            problems.append(f"dup-old_system_ref: '{ref}' 出现在多叶 {ids}")
    if problems:
        for p in problems:
            print(p, file=sys.stderr)
        print(f"\nlint: {len(problems)} 个问题", file=sys.stderr)
        return 1
    print("lint: clean")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="sdlc-backlog 需求树派生操作")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("readyqueue", "coverage", "lint"):
        p = sub.add_parser(name)
        p.add_argument("--root", required=True, help=".sdlc/requirements 目录")
    args = ap.parse_args(argv)
    if not os.path.isdir(args.root):
        print(f"root 不存在: {args.root}", file=sys.stderr)
        return 2
    return {"readyqueue": cmd_readyqueue, "coverage": cmd_coverage,
            "lint": cmd_lint}[args.cmd](args.root)


if __name__ == "__main__":
    sys.exit(main())
