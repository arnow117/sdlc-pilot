#!/usr/bin/env python3
"""sdlc-backlog 派生操作 — readyqueue / coverage / lint.

读 <root>/<domain>/<subdomain>/<leaf>.md 的 frontmatter(事实源),机械派生:
  readyqueue : 解依赖的就绪叶(A/B 契约),JSON 到 stdout
  coverage   : 按 domain 的 status 计数 burndown,JSON 到 stdout
  lint       : 断依赖 / 重复 old_system_ref / 缺字段 / 孤儿;有问题则非 0 退出
  retire     : 特性退场(close-out)——归档 .sdlc 工件 + 标源叶 shipped + 回流追加 + 清栈

纯标准库,无第三方依赖(可移植:Claude / Codex 都能跑)。
事实源 = 叶 frontmatter;派生操作(readyqueue/coverage/lint)只读;
retire 写树(标 shipped)+ 移工件 + 回流追加。
"""
import argparse
import json
import os
import re
import shutil
import sys

REQUIRED_FIELDS = [
    "id", "title", "domain_path", "cross_link", "old_system_ref",
    "new_domain_path", "status", "priority", "depends_on", "risk_level",
]
PRIORITY_ORDER = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}
SHIPPED = "shipped"
RETIRE_ARTIFACTS = ["spec.md", "plan.md", "validate", "review", "STATE.md"]


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


TREE_LEAF_KEYS = [
    "id", "title", "status", "priority", "risk_level",
    "depends_on", "old_system_ref", "new_domain_path", "cross_link",
]


def build_tree(leaves):
    """把扁平叶 list 组装成 domain→subdomain→leaf 嵌套树 + summary。board 与 tree 共用。"""
    by_id = {lf.get("id"): lf for lf in leaves}

    def _is_ready(lf):
        if lf.get("status") == SHIPPED:
            return False
        deps = lf.get("depends_on") or []
        return all(by_id.get(d, {}).get("status") == SHIPPED for d in deps)

    doms = {}            # domain -> {subdomain -> [leaf dict]}（dict 保序）
    by_status = {}
    for lf in leaves:
        dp = lf.get("domain_path") or os.path.dirname(lf.get("_path", ""))
        parts = dp.split("/") if dp else [""]
        dom = parts[0] or "(未分类)"
        sub = parts[1] if len(parts) > 1 else "(根)"
        doms.setdefault(dom, {}).setdefault(sub, []).append(
            {k: lf.get(k) for k in TREE_LEAF_KEYS})
        st = lf.get("status", "unknown")
        by_status[st] = by_status.get(st, 0) + 1
    domains = [
        {"domain": dom,
         "subdomains": [{"subdomain": sub, "leaves": lvs} for sub, lvs in subs.items()]}
        for dom, subs in doms.items()
    ]
    return {
        "domains": domains,
        "summary": {
            "total": len(leaves),
            "by_status": by_status,
            "ready_count": sum(1 for lf in leaves if _is_ready(lf)),
        },
    }


def cmd_tree(root):
    print(json.dumps(build_tree(load_leaves(root)), ensure_ascii=False, indent=2))
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


def _set_frontmatter_status(path, value):
    """把叶文件首块 frontmatter 的首个 `status:` 行改成 value,写回(count=1 只改首行)。"""
    with open(path, encoding="utf-8") as f:
        text = f.read()
    new = re.sub(r"(?m)^status:.*$", f"status: {value}", text, count=1)
    with open(path, "w", encoding="utf-8") as f:
        f.write(new)


def _mark_leaf_shipped(req_root, leaf_id):
    """源叶 status -> shipped。命中返回 True,未命中返回 False。"""
    for lf in load_leaves(req_root):
        if lf.get("id") == leaf_id:
            _set_frontmatter_status(os.path.join(req_root, lf["_path"]), SHIPPED)
            return True
    return False


def _append_evolution(sdlc_dir, entry):
    """耐久教训回流:统一 append `<sdlc>/EVOLUTION.md`(唯一正屋;缺则建 `# Evolution log` 头)。
    PROFILE 不承载流水(仅留指针)——见 templates/PROFILE.md。"""
    target = os.path.join(sdlc_dir, "EVOLUTION.md")
    exists = os.path.isfile(target)
    with open(target, "a", encoding="utf-8") as f:
        if not exists:
            f.write("# Evolution log\n\n")
        f.write(entry + "\n")
    return target


def cmd_move(args):
    """叶迁域:mv 文件 + 改 id/domain_path + 改写全树指向旧 id 的 depends_on。确定性写 op(仿 retire)。
    源叶不存在 → 2;目标已存在同 id → 1 拒绝(幂等守卫),均不动文件。"""
    leaves = load_leaves(args.root)
    by_id = {lf.get("id"): lf for lf in leaves}
    src = by_id.get(args.leaf)
    if not src:
        print(f"源叶不存在: {args.leaf}", file=sys.stderr)
        return 2
    slug = args.leaf.split(".")[-1]
    new_dp = args.to.strip("/")                       # "<domain>/<subdomain>"
    new_id = new_dp.replace("/", ".") + "." + slug
    new_dir = os.path.join(args.root, *new_dp.split("/"))
    new_path = os.path.join(new_dir, new_id + ".md")
    if os.path.exists(new_path):
        print(f"目标已存在,拒绝覆盖: {new_path}", file=sys.stderr)
        return 1
    old_path = os.path.join(args.root, src["_path"])
    with open(old_path, encoding="utf-8") as f:
        text = f.read()
    text = re.sub(r"(?m)^id:.*$", f"id: {new_id}", text, count=1)
    text = re.sub(r"(?m)^domain_path:.*$", f"domain_path: {new_dp}", text, count=1)
    os.makedirs(new_dir, exist_ok=True)
    with open(new_path, "w", encoding="utf-8") as f:
        f.write(text)
    os.remove(old_path)
    rewritten = 0
    for lf in leaves:                                 # 改写其余叶对旧 id 的 depends_on 引用
        if lf.get("id") == args.leaf:
            continue
        if args.leaf in (lf.get("depends_on") or []):
            p = os.path.join(args.root, lf["_path"])
            with open(p, encoding="utf-8") as f:
                t = f.read()
            t = re.sub(r"(?m)^(depends_on:.*)$",
                       lambda m: m.group(1).replace(args.leaf, new_id), t, count=1)
            with open(p, "w", encoding="utf-8") as f:
                f.write(t)
            rewritten += 1
    print(json.dumps({"moved": args.leaf, "to": new_id, "deps_rewritten": rewritten},
                     ensure_ascii=False))
    return 0


def cmd_retire(args):
    """特性退场:①归档工件 ②标源叶 shipped(可选) ③回流追加(可选) ④清栈。幂等:archive 已存在则拒绝。"""
    archive_dir = os.path.join(args.sdlc, "archive", f"{args.date}-{args.slug}")
    if os.path.exists(archive_dir):
        print(f"archive 已存在,拒绝覆盖: {archive_dir}", file=sys.stderr)
        return 1
    os.makedirs(archive_dir)
    moved = []
    for name in RETIRE_ARTIFACTS:  # ①归档 + ④清栈(move 走顶层即清空)
        src = os.path.join(args.sdlc, name)
        if os.path.exists(src):
            shutil.move(src, os.path.join(archive_dir, name))
            moved.append(name)
    leaf_shipped = False
    if args.leaf and args.req_root:  # ③标 shipped(优雅降级:无叶/无树则跳过)
        leaf_shipped = _mark_leaf_shipped(args.req_root, args.leaf)
        if not leaf_shipped:
            print(f"warn: 未找到源叶 '{args.leaf}',跳过标 shipped", file=sys.stderr)
    backflow = None
    if args.evolution_entry:  # ②回流(内容由调用方蒸馏,目标选择确定性)
        backflow = _append_evolution(args.sdlc, args.evolution_entry)
    print(json.dumps({"archived": archive_dir, "moved": moved,
                      "leaf_shipped": leaf_shipped, "backflow": backflow},
                     ensure_ascii=False))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="sdlc-backlog 需求树派生操作")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("readyqueue", "coverage", "lint", "tree"):
        p = sub.add_parser(name)
        p.add_argument("--root", required=True, help=".sdlc/requirements 目录")
    pr = sub.add_parser("retire", help="特性退场:归档 + 标叶 shipped + 回流 + 清栈")
    pr.add_argument("--sdlc", required=True, help=".sdlc 目录")
    pr.add_argument("--slug", required=True, help="特性 slug(归档目录名用)")
    pr.add_argument("--date", required=True, help="日期 YYYY-MM-DD(归档目录名用)")
    pr.add_argument("--leaf", help="源叶 id(给则标 shipped)")
    pr.add_argument("--req-root", dest="req_root", help="requirements 树根(配合 --leaf)")
    pr.add_argument("--evolution-entry", dest="evolution_entry",
                    help="回流到 Evolution log 的一行(由调用方蒸馏)")
    pm = sub.add_parser("move", help="叶迁域:mv 文件 + 改 id/domain_path + 改写依赖")
    pm.add_argument("--root", required=True, help=".sdlc/requirements 目录")
    pm.add_argument("--leaf", required=True, help="要迁移的叶 id")
    pm.add_argument("--to", required=True, help="目标 <domain>/<subdomain>")
    args = ap.parse_args(argv)
    if args.cmd == "retire":
        return cmd_retire(args)
    if not os.path.isdir(args.root):
        print(f"root 不存在: {args.root}", file=sys.stderr)
        return 2
    if args.cmd == "move":
        return cmd_move(args)
    return {"readyqueue": cmd_readyqueue, "coverage": cmd_coverage,
            "lint": cmd_lint, "tree": cmd_tree}[args.cmd](args.root)


if __name__ == "__main__":
    sys.exit(main())
