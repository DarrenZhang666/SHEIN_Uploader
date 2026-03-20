# SHEIN 商品采集 & 发布工具 - 打包为 EXE
# 运行此脚本前请先安装依赖：pip install -r requirements.txt pyinstaller

pyinstaller --noconfirm --onefile --windowed --name "SHEIN上品工具" Software.py
