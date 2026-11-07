# Project Overview

A locally hosted project dashboard that imports an Excel or CSV project list and displays an overview, project timelines, and project details.

## Start

1. Install Python and the dependencies: `python -m pip install -r backend/requirements.txt`.
2. On Windows, run `启动项目概览.bat` and open `http://127.0.0.1:18765/`. Alternatively, from the `backend` directory run `python -m uvicorn app:app --host 127.0.0.1 --port 18765`.
3. In Settings, select a source `.xlsx` or `.csv` file. The application reads saved values and does not refresh external Excel links or recalculate formulas.

Data is processed locally; source workbooks and Power BI files are intentionally not part of this repository. The application is designed for local use and does not provide authentication or multi-user access control.

See `backend/README.md` for further notes.
