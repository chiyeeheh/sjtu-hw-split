#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""第一步：把作业 PDF 拆成「行」，并生成给人/模型看的图。

    python prepare.py <pdf> <工作区目录> [--dpi 200] [--per-sheet 14]

产出（全部写进工作区目录）：
    页_01.png         整页 + 左边距坐标标尺（读某一行在哪儿用）
    候选_01.png       左边距候选行的对照表，每格标着 p页 L行号 y坐标
    行坐标.json       每页每一行的 y0/y1/x0/x1，给 cut.py 用

stdout（每行一条，方便解析）：
    PAGE  <页号> <宽>x<高> <整页标尺图路径>
    SHEET <序号> <候选对照表路径>
    CANDS <候选行数>
    LINES <行坐标.json 路径>
    DONE  <页数>页 <总行数>行
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import hw_geom as G


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf")
    ap.add_argument("workdir")
    ap.add_argument("--dpi", type=int, default=G.DPI)
    ap.add_argument("--per-sheet", type=int, default=14,
                    help="每张候选对照表放多少行")
    args = ap.parse_args()

    os.makedirs(args.workdir, exist_ok=True)
    pdf = G.Pdf(args.pdf, args.dpi)
    pages = G.analyse(pdf)

    for p in pages:
        im = G.ruler_page(pdf, p)
        path = os.path.join(args.workdir, "页_%02d.png" % p["page"])
        im.save(path)
        print("PAGE %d %dx%d %s" % (p["page"], im.width, im.height, path))

    cands = G.pick_candidates(pages)
    sheets = G.candidate_sheet(pdf, cands, per_sheet=args.per_sheet)
    for i, (chunk, sheet) in enumerate(sheets, 1):
        path = os.path.join(args.workdir, "候选_%02d.png" % i)
        sheet.save(path)
        print("SHEET %d %s" % (i, path))
    print("CANDS %d" % len(cands))

    lines_path = os.path.join(args.workdir, "行坐标.json")
    with open(lines_path, "w", encoding="utf-8") as f:
        json.dump({"dpi": args.dpi,
                   "pdf": os.path.abspath(args.pdf),
                   "pages": pages}, f, ensure_ascii=False, indent=1)
    print("LINES %s" % lines_path)
    print("DONE %d页 %d行" % (len(pages), sum(len(p["lines"]) for p in pages)))


if __name__ == "__main__":
    main()
