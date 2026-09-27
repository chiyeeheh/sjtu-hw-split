#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""作业 PDF 分题的共用几何工具。

只做「像素层面」的事：渲染、按墨迹切行、找候选行、裁图拼接。
**不判断哪一行是大题开头**——那是读图的模型（Claude）干的活。
"""

import os

import numpy as np
from PIL import Image, ImageDraw, ImageFont

DPI = 200
MIN_MARK = 3          # 判定「这一行有字」的最少暗像素数（200 DPI 下取 3）
PAD_X = 22            # 左右留白（像素）
PAD_Y = 10            # 上下留白（像素）


# ---------------------------------------------------------------- 基础

def font(size=18):
    for name in ("msyh.ttc", "simhei.ttf", "arial.ttf"):
        p = os.path.join(os.environ.get("WINDIR", "C:/Windows"), "Fonts", name)
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                pass
    return ImageFont.load_default()


class Pdf:
    """按页渲染 PDF，只缓存当前一页，避免大文档吃内存。"""

    def __init__(self, path, dpi=DPI):
        import pymupdf
        self.doc = pymupdf.open(path)
        self.dpi = dpi
        self._cache = {}

    def __len__(self):
        return self.doc.page_count

    def page(self, i):
        if i not in self._cache:
            pix = self.doc[i].get_pixmap(dpi=self.dpi)
            arr = np.frombuffer(pix.samples, dtype=np.uint8)
            arr = arr.reshape(pix.height, pix.width, pix.n)[:, :, :3].copy()
            self._cache = {i: arr}
        return self._cache[i]

    def mask(self, i):
        """墨迹掩膜：暗于背景中位数的 55% 记 True（自适应纸张明暗）。"""
        lum = self.page(i).mean(axis=2)
        return lum < float(np.median(lum)) * 0.55


def _runs(flags):
    """连续 True 段 → [(起, 止)]（止为开区间）。"""
    out, s = [], None
    for i, v in enumerate(flags):
        if v and s is None:
            s = i
        elif not v and s is not None:
            out.append((s, i))
            s = None
    if s is not None:
        out.append((s, len(flags)))
    return out


# ---------------------------------------------------------------- 版面分析

def content_bounds(mask):
    """正文区上下边界：只砍掉贴底的**页脚**，不动页眉。

    页眉不用管——它顶多让页首多出两行候选（印刷的标题和日期），
    读图时会一眼排除；而一旦把页眉猜错，代价是**整行手写内容被悄悄切掉**。
    实测两种猜法都踩过坑：第 9 页开头那行算式续行、第 2 页开头那行，
    都因为「窄 + 贴顶」被误判成页眉而丢失。所以这里干脆不猜页眉。

    页脚保留判断，因为它是真的会跑到最后一张图里去。判据加上「矮」——
    印刷小字只有二十来像素高，手写一行普遍更高。
    """
    H = mask.shape[0]
    bands = _runs(mask.sum(axis=1) >= MIN_MARK)
    if not bands:
        return 0, H
    bot = H

    if len(bands) >= 2:
        last = bands[-1]
        xs = np.nonzero(mask[last[0]:last[1]].sum(axis=0))[0]
        gaps = [bands[i + 1][0] - bands[i][1] for i in range(len(bands) - 1)]
        med = float(np.median(gaps)) if gaps else 0.0
        narrow = (xs[-1] - xs[0]) < 0.5 * mask.shape[1] if len(xs) else False
        centered = (xs[0] > 0.1 * mask.shape[1]) if len(xs) else False
        if (last[0] > 0.93 * H and narrow and centered
                and (last[1] - last[0]) < 0.02 * H
                and (last[0] - bands[-2][1]) > max(1.6 * med, 0.012 * H)):
            bot = last[0] - max(int(0.004 * H), 4)

    return 0, int(bot)


def line_boxes(mask, top, bot):
    """正文区切成一行行 → [(y0, y1)]。

    同一行偶尔会被切成好几段（数字顶端、分数线两侧的空白）。
    判据是**碎片本身很薄**才并回下一段；只看间隔小会把上下两行正常文字误并
    （试过，准确率反而下降）。
    """
    H = mask.shape[0]
    gap = max(6, int(H * 0.006))
    thin = max(6, int(H * 0.0035))
    merged = []
    for (a, b) in _runs(mask[top:bot].sum(axis=1) >= MIN_MARK):
        if merged and (merged[-1][1] - merged[-1][0]) < thin and a - merged[-1][1] <= gap:
            merged[-1][1] = b
        else:
            merged.append([a, b])
    return [(a + top, b + top) for a, b in merged]


def line_xextent(mask, y0, y1):
    """某行的 (起笔 x, 收笔 x)。起笔用较严阈值，避开很淡的横格线。"""
    band = mask[y0:y1]
    cols = band.sum(axis=0)
    nz = np.nonzero(cols)[0]
    if not len(nz):
        return None
    strong = np.nonzero(cols > max(1, (y1 - y0) * 0.04))[0]
    return int(strong[0]) if len(strong) else int(nz[0]), int(nz[-1])


def analyse(pdf):
    """全篇跑一遍，返回每页的正文范围与逐行信息。"""
    pages = []
    for i in range(len(pdf)):
        mask = pdf.mask(i)
        top, bot = content_bounds(mask)
        lines = []
        for (y0, y1) in line_boxes(mask, top, bot):
            ext = line_xextent(mask, y0, y1)
            if ext is None:
                continue
            lines.append({"y0": int(y0), "y1": int(y1),
                          "x0": ext[0], "x1": ext[1]})
        pages.append({"page": i + 1, "top": top, "bot": bot,
                      "w": int(mask.shape[1]), "h": int(mask.shape[0]),
                      "lines": lines})
    return pages


def pick_candidates(pages):
    """行首明显靠左的行 → 候选。大题题号总是写在最左边那一列。

    阈值取「本页行首 x 的 30 百分位」而不是全篇固定值：不同作业的左边距、
    小问缩进都不一样。实测这份作业上该判据保留了全部 20 道大题的首行，
    同时把候选从 349 行压到 104 行，读图时省很多事。
    """
    cands = []
    for p in pages:
        lines = p["lines"]
        if not lines:
            continue
        xs = [l["x0"] for l in lines]
        limit = float(np.percentile(xs, 30)) if len(xs) >= 4 else float(max(xs))
        for li, l in enumerate(lines):
            if l["y1"] - l["y0"] < 8:          # 太薄 → 只是笔画碎片
                continue
            if l["x0"] < limit:
                cands.append({"page": p["page"], "li": li,
                              "y0": l["y0"], "y1": l["y1"]})
    return cands


# ---------------------------------------------------------------- 给模型看的图

def ruler_page(pdf, p, scale=0.75, step=100):
    """整页 + 左边距坐标标尺，用来读某一行到底在哪。"""
    img = pdf.page(p["page"] - 1)
    im = Image.fromarray(img)
    if scale != 1.0:
        im = im.resize((int(im.width * scale), int(im.height * scale)), Image.LANCZOS)
    d = ImageDraw.Draw(im)
    f = font(15)
    for y in range(step, im.height, step):
        d.line([(0, y), (60, y)], fill=(255, 0, 0), width=1)
        d.text((62, y - 9), str(int(y / scale)), fill=(200, 0, 0), font=f)
    return im


def candidate_sheet(pdf, cands, per_sheet=14, crop_w=900, pad=8):
    """候选行的「行首」按顺序拼成对照表，每格标注 p页 L行号 y坐标。"""
    f = font(20)
    sheets = []
    for s in range(0, len(cands), per_sheet):
        chunk = cands[s:s + per_sheet]
        rows = []
        for c in chunk:
            img = pdf.page(c["page"] - 1)
            y0 = max(0, c["y0"] - pad)
            y1 = min(img.shape[0], c["y1"] + pad + 2)
            rows.append(img[y0:y1, 40:40 + crop_w])
        sheet = Image.new("RGB", (crop_w + 156, sum(r.shape[0] + 30 for r in rows)),
                          "white")
        d = ImageDraw.Draw(sheet)
        yy = 0
        for c, r in zip(chunk, rows):
            d.rectangle([0, yy, 150, yy + 27], fill=(255, 246, 205))
            d.text((5, yy + 3), "p%d L%d y%d" % (c["page"], c["li"], c["y0"]),
                   fill=(150, 90, 0), font=f)
            yy += 30
            sheet.paste(Image.fromarray(r), (152, yy))
            yy += r.shape[0]
        sheets.append((chunk, sheet))
    return sheets


# ---------------------------------------------------------------- 下刀与拼接

def cut_before(pages, page_idx, y):
    """上一题末尾与本行之间的空白带中点 —— 在这一刀上谁都不会被切到。"""
    prev = [l for l in pages[page_idx]["lines"] if l["y1"] <= y]
    return (prev[-1]["y1"] + y) // 2 if prev else pages[page_idx]["top"]


def build_segments(pages, marks):
    """marks: [(页号1起, 首行 y)] 按顺序。返回每题 [(页0起, y0, y1)] 片段表。"""
    last = len(pages)
    out = []
    for k, (pg1, y0) in enumerate(marks):
        pi = pg1 - 1
        segs = [[pi, cut_before(pages, pi, y0), None]]
        if k + 1 < len(marks):
            npg1, ny0 = marks[k + 1]
            npi = npg1 - 1
            if npi == pi:
                segs[0][2] = cut_before(pages, npi, ny0)
            else:
                for mp in range(pi + 1, npi):
                    segs.append([mp, pages[mp]["top"], None])
                segs.append([npi, pages[npi]["top"], cut_before(pages, npi, ny0)])
        else:
            for mp in range(pi + 1, last):
                segs.append([mp, pages[mp]["top"], None])
        filled = []
        for (p, a, b) in segs:
            lines = pages[p]["lines"]
            if b is None:
                b = min(lines[-1]["y1"] + PAD_Y, pages[p]["bot"]) if lines \
                    else pages[p]["bot"]
            # 从页顶接下去的那一段（跨页续写），贴着该页第一行起，别留一大片空白
            if a == pages[p]["top"] and lines:
                a = max(a, lines[0]["y0"] - PAD_Y)
            filled.append((p, max(a, pages[p]["top"]), b))
        out.append(filled)
    return out


def render_one(pdf, segs):
    """裁一段（可能跨页拼接）→ PIL 图。左右范围取所有片段的并集，保证对齐。"""
    xlo, xhi = 10 ** 9, -1
    for (p, y0, y1) in segs:
        cols = np.nonzero(pdf.mask(p)[y0:y1 + 1].sum(axis=0))[0]
        if len(cols):
            xlo, xhi = min(xlo, int(cols[0])), max(xhi, int(cols[-1]))
    if xhi < 0:
        return None
    w = pdf.page(0).shape[1]
    x0, x1 = max(xlo - PAD_X, 0), min(xhi + PAD_X, w - 1)
    parts = [pdf.page(p)[y0:y1 + 1, x0:x1 + 1] for (p, y0, y1) in segs]
    arr = parts[0] if len(parts) == 1 else np.concatenate(parts, axis=0)
    return Image.fromarray(arr.astype(np.uint8))


def overview(results, path):
    """校对总览：上排每张图的开头（应恰好是题号），下排每张图的结尾。"""
    if not results:
        return None
    f = font(24)
    CW, CH = 660, 210
    cols = 2
    rows = (len(results) + cols - 1) // cols
    sheet = Image.new("RGB", (CW * cols, CH * rows * 2 + 60), "white")
    d = ImageDraw.Draw(sheet)
    d.text((10, 8), "上排：每张图的开头（应恰好是题号）｜下排：每张图的结尾",
           fill=(180, 0, 0), font=f)
    for i, (name, img) in enumerate(results):
        for half in (0, 1):
            strip = img.crop((0, 0, img.width, min(230, img.height))) if half == 0 \
                else img.crop((0, max(0, img.height - 230), img.width, img.height))
            strip.thumbnail((CW - 8, CH - 8), Image.LANCZOS)
            cx = (i % cols) * CW
            cy = 60 + half * CH * rows + (i // cols) * CH
            sheet.paste(strip, (cx + 4, cy + 4))
            d.rectangle([cx, cy, cx + CW - 1, cy + CH - 1], outline=(185, 185, 185))
            d.text((cx + CW - 120, cy + 4),
                   name.replace("第", "").replace("题.png", ""),
                   fill=(200, 0, 0), font=f)
    sheet.save(path)
    return path
