# sjtu-hw-split

把作业 PDF **按大题裁成一张张图片**（每题一张，跨页自动拼接），保留手写原貌，不做任何识别或重排。

这是给 [Claude Code](https://claude.com/claude-code) 用的 skill。

## 效果

一份 11 页的手写作业 PDF 进去，出来 `第01题.png`、`第02题.png`……每一张恰好是一道大题，
小问 `(1) (2)`、`①②③` 跟所属大题合并；一道题写满一页接着下一页的，自动竖向拼成一张。
另外附一张 `_校对总览.png`，上排是每张图的开头、下排是结尾，方便一眼复核。

## 原理

| 谁 | 做什么 |
|---|---|
| **脚本** | 只做像素层面的事：渲染、切行、裁图拼接。所以边界永远精确，下刀位置一定落在两题之间的空白带上，不会切到字 |
| **Claude** | 负责唯一需要判断力的一步：看对照表，指出哪一行是大题的**开头** |

脚本先渲染 PDF，把每页切成行，再拼成若干张「候选行对照表」，每格是一行的行首，
左上角标着坐标。Claude 逐格判断「这是一个顶层题号（`3.`）还是小问编号（`(3)`）还是正文续行」，
把选中的边界写成 JSON，脚本据此裁图。

**不联网、不调 API、不依赖 PDF 有没有文字层** —— 扫描件、拍照件一样能用。

## 安装

```bash
mkdir -p ~/.claude/skills
git clone https://github.com/chiyeeheh/sjtu-hw-split.git ~/.claude/skills/sjtu-hw-split
python -m pip install pymupdf pillow numpy
```

第一条是给目录兜底——`~/.claude/skills/` 不存在的话，直接 `cp` 进去会报
`cannot create directory`，所以先建出来。第二条直接把仓库克隆到技能目录里，
不用先 clone 再 cp。

几个坑：

- **Windows 的 cmd / PowerShell 不认 `~` 和 `mkdir -p`。** 用 Git Bash 跑，
  或者把路径换成 `%USERPROFILE%\.claude\skills\sjtu-hw-split`
- 如果 `python` 不对，换成 `python3 -m pip install pymupdf pillow numpy`
- 装完要**重开一个 Claude Code 会话**才会加载
- 以后更新：`git -C ~/.claude/skills/sjtu-hw-split pull`

## 用法

直接说人话就行：

> 把 ~/Downloads/高数作业.pdf 按题切开

或者点名调用：`/sjtu-hw-split`

Claude 会自己找 PDF、建工作区、读对照表挑边界、裁图，最后打开校对总览复核。

## 产物

```
<PDF 所在目录>/
├── _切图工作区/            ← 中间产物，可以删
│   ├── 页_01.png            整页 + 左边距坐标标尺
│   ├── 候选_01.png          候选行对照表
│   └── 行坐标.json
├── <PDF名>_按题分区/
│   └── 第01题.png …
└── <PDF名>_校对总览.png     ← 复核用的总览图
```

## 和 sjtu-hw-to-latex 的区别

| | **sjtu-hw-split**（本仓库） | sjtu-hw-to-latex |
|---|---|---|
| 做什么 | 裁原图 | 识别成 LaTeX，订正，再渲染 |
| 输出 | 原始扫描图的裁切 | `.tex` / `.txt` + 重新排版的图 |
| 手写原貌 | **保留** | 丢失 |
| 依赖 | pymupdf / pillow / numpy | 额外要 Node + Chrome |

**要认字就用 to-latex，只要图就用 split。** 交作业要手写原貌 → 本仓库；
要干净排版、或者想让它帮你查错 → 用 `sjtu-hw-to-latex` 那个 skill。

> 两个 skill 是配套的，可以都装。安装方式和上面一样，仓库名就是 `sjtu-hw-to-latex`。
