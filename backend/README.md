# 本地项目概览

双击上级目录的 `启动项目概览.bat`，等待命令窗口显示服务启动；若浏览器打开过早，请刷新 `http://127.0.0.1:18765/`。关闭命令窗口即可停止服务。也可在 backend 目录执行 `python -m uvicorn app:app --host 127.0.0.1 --port 18765`，然后访问该地址。

依赖：`python -m pip install -r backend/requirements.txt`。支持 .xlsx 和 CSV，CSV 需提供与源 Excel 相同字段。Excel 读取保存的公式缓存，不刷新外部数据或重算公式。文件仅发往本机服务，导入结果保存在当前网页内存；刷新网页需要重新选择文件。

初步页面已接入真实数据和三个公共筛选器。项目时间线已提供甘特图，部分页面专属筛选已接入；原报表固定日期条件、完整交叉筛选和逐页 Power BI 对账尚未完成。不要把当前页面视作已完全复刻 Power BI。


## Document Check

在 Workspace 左侧选择“Document Check”，上传单个 PDF（最大 60 MB）并点击“开始检查”。该功能沿用 Checker 的检查规则，依赖 PyMuPDF；PDF 在本机内存中处理，不支持扫描件 OCR，需人工核对不确定的结果。
