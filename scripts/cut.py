#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""第二步：按给定的「大题首行」下刀，切图 + 生成校对总览。

    python cut.py <pdf> <工作区目录> <边界.json> [--out <图片目录>]

边界.json 由读图的那一步产出，列出每道大题的首行，按先后顺序：
    [{"page": 1, "line": 2,  "num": 1},
     {"page": 2, "line": 17, "num": 2},
     {"page": 2, "line": 22, "num": 3}]

- `line` 是「行坐标.json」里该页的行号（从 0 开始），也可以直接给 `y` 像素坐标；
- `num` 可省略；齐全且递增时用它命名图片，否则按出现顺序编号。

产物（默认写到 PDF 旁边的 <PDF名>_按题分区/）：
    第01题.png …        每道大题一张，跨页的竖向拼成一张
    <PDF名>_校对总览.png  上排看开头、下排看结尾，用来核对切得对不对

stdout：
    IMG <题号> <宽>x<高> <路径>
    OVERVIEW <路径>
    DONE <张数>
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
    ap.add_argument("bounds", help="边界.json")
    ap.add_argument("--out", default=None, help="图片输出目录")
    args = ap.parse_args()

    with open(os.path.join(args.workdir, "行坐标.json"), encoding="utf-8") as f:
        data = json.load(f)
    pages = data["pages"]

    with open(args.bounds, encoding="utf-8") as f:
        items = json.load(f)
    if isinstance(items, dict):
        items = items.get("questions", [])

    marks, nums = [], []
    for it in items:
        pg = int(it["page"])
        if pg < 1 or pg > len(pages):
            print("SKIP 第%d页不存在" % pg, file=sys.stderr)
            continue
        if "line" in it and it["line"] is not None:
            li = int(it["line"])
            if not (0 <= li < len(pages[pg - 1]["lines"])):
                print("SKIP p%d L%d 越界" % (pg, li), file=sys.stderr)
                continue
            y0 = pages[pg - 1]["lines"][li]["y0"]
        else:
            y0 = int(it["y"])
        marks.append((pg, y0))
        nums.append(it.get("num"))

    order = sorted(range(len(marks)), key=lambda i: marks[i])
    marks = [marks[i] for i in order]
    nums = [nums[i] for i in order]
    if not marks:
        print("没有有效边界", file=sys.stderr)
        return 1

    name = os.path.splitext(os.path.basename(args.pdf))[0]
    outdir = args.out or os.path.join(os.path.dirname(os.path.abspath(args.pdf)),
                                      name + "_按题分区")
    os.makedirs(outdir, exist_ok=True)

    seq = list(range(1, len(marks) + 1))
    if (len(nums) == len(marks) and all(isinstance(n, int) and n > 0 for n in nums)
            and nums == sorted(set(nums))):
        seq = nums
    width = max(2, len(str(max(seq))))

    pdf = G.Pdf(args.pdf, data.get("dpi", G.DPI))
    results = []
    for k, segs in enumerate(G.build_segments(pages, marks)):
        img = G.render_one(pdf, segs)
        if img is None:
            continue
        fname = "第%s题.png" % str(seq[k]).zfill(width)
        path = os.path.join(outdir, fname)
        img.save(path)
        results.append((fname, img))
        print("IMG %s %dx%d %s" % (seq[k], img.width, img.height, path))

    ov = os.path.join(os.path.dirname(os.path.abspath(args.pdf)),
                      name + "_校对总览.png")
    G.overview(results, ov)
    print("OVERVIEW %s" % ov)
    print("DONE %d" % len(results))


if __name__ == "__main__":
    main()
