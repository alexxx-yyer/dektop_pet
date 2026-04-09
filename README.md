# 奇魔小小猪 - 桌面宠物

一只会在屏幕上走来走去、可以拖拽甩飞、还能传送的桌面宠物小猪。

## 功能

- 自动在屏幕底部漫游行走
- 鼠标拖拽抓起，松手可甩飞（带物理弹跳）
- 靠近屏幕边缘自动停靠
- 随机触发传送门，瞬移到屏幕其他位置
- 系统托盘图标，右键可显示/隐藏/退出

## 环境配置

需要 Python 3.10+，推荐使用 conda 或 venv 创建虚拟环境。

```bash
# 创建并激活虚拟环境（conda）
conda create -n kimo python=3.12 -y
conda activate kimo

# 或使用 venv
python -m venv .venv
source .venv/bin/activate  # macOS/Linux
# .venv\Scripts\activate   # Windows
```

安装依赖：

```bash
pip install PyQt6

# macOS 还需要安装（用于窗口置顶和隐藏 Dock 图标）
pip install pyobjc-framework-Cocoa
```

## 运行

```bash
python pet.py
```

启动后小猪会出现在屏幕底部，系统托盘会显示图标。

- **左键拖拽** — 抓起小猪，松手甩飞
- **右键菜单** — 隐藏 / 退出
- **托盘图标** — 右键可重新显示小猪

## 打包为应用（可选）

```bash
pip install pyinstaller

# macOS（生成 .app）
pyinstaller 奇魔小小猪.spec

# Windows
pyinstaller --noconsole --add-data "gifs;gifs" pet.py
```

打包产物在 `dist/` 目录下。

## 项目结构

```
pet.py          # 主程序源码
gifs/           # 动画资源
  walk_left.gif
  walk_right.gif
  struggle.gif
```
