"""Local read-only import API. FastAPI when installed, Starlette fallback."""
from pathlib import Path
from starlette.requests import Request
from starlette.responses import JSONResponse, FileResponse
from starlette.routing import Route
from processing import process, ImportProblem

async def index(request: Request):
    return FileResponse(Path(__file__).resolve().parent.parent / 'web-preview' / 'index.html', headers={'Cache-Control':'no-store'})

async def logo(request: Request):
    return FileResponse(Path(__file__).resolve().parent.parent / 'Bosch-logo.png', media_type='image/png')

async def overview_icon(request: Request):
    return FileResponse(Path(__file__).resolve().parent.parent / 'overview.png', media_type='image/png')

async def settings_icon(request: Request):
    return FileResponse(Path(__file__).resolve().parent.parent / 'shezhi.png', media_type='image/png')

async def health(request: Request):
    return JSONResponse({'status':'ok','service':'project-overview-import'})

async def import_file(request: Request):
    try:
        form=await request.form(max_files=1, max_fields=5, max_part_size=25*1024*1024)
        upload=form.get('file')
        if upload is None or not hasattr(upload,'read'): return JSONResponse({'error':'请选择源文件。'},status_code=400)
        data=await upload.read(25*1024*1024+1)
        if len(data)>25*1024*1024: return JSONResponse({'error':'文件超过 25 MB。'},status_code=413)
        return JSONResponse(process(upload.filename or '',data))
    except ImportProblem as exc: return JSONResponse({'error':str(exc)},status_code=422)
    except Exception: return JSONResponse({'error':'文件处理失败，请检查文件格式。'},status_code=400)

try:
    from fastapi import FastAPI
    app=FastAPI(title='Project Overview Import API')
    app.add_api_route('/',index,methods=['GET'],include_in_schema=False)
    app.add_api_route('/assets/bosch-logo.png',logo,methods=['GET'],include_in_schema=False)
    app.add_api_route('/assets/overview.png',overview_icon,methods=['GET'],include_in_schema=False)
    app.add_api_route('/assets/settings.png',settings_icon,methods=['GET'],include_in_schema=False)
    app.add_api_route('/health',health,methods=['GET'])
    app.add_api_route('/api/import',import_file,methods=['POST'])
except ImportError:
    from starlette.applications import Starlette
    app=Starlette(routes=[Route('/',index),Route('/assets/bosch-logo.png',logo),Route('/assets/overview.png',overview_icon),Route('/assets/settings.png',settings_icon),Route('/health',health),Route('/api/import',import_file,methods=['POST'])])
