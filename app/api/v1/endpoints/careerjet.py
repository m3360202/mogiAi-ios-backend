"""
CareerJet API 代理端点
通过后端代理 CareerJet API 请求，解决 IP 验证问题
"""
import os
import base64
from typing import Optional
from fastapi import APIRouter, HTTPException, Request, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import httpx

router = APIRouter()

# CareerJet API 配置
CAREERJET_API_URL = "https://search.api.careerjet.net/v4/query"
CAREERJET_API_KEY = os.getenv("CAREERJET_API_KEY", "")
CAREERJET_REFERER = os.getenv("CAREERJET_REFERER", "https://careerface.app")

# 网关模式配置：
# - direct: 当前服务直接调用 CareerJet 官方 API（需要静态 IP / NAT）
# - proxy: 当前服务转发到专用网关服务，由网关去调用 CareerJet
CAREERJET_MODE = os.getenv("CAREERJET_MODE", "direct")  # direct | proxy
CAREERJET_GATEWAY_BASE_URL = os.getenv("CAREERJET_GATEWAY_BASE_URL", "")


class CareerJetSearchRequest(BaseModel):
    """CareerJet 搜索请求"""
    keywords: Optional[str] = None
    location: Optional[str] = "日本"
    locale_code: Optional[str] = "ja_JP"
    contract_type: Optional[str] = None
    work_hours: Optional[str] = None
    page_size: Optional[int] = 20
    page: Optional[int] = 1
    offset: Optional[int] = 0
    radius: Optional[int] = 5
    fragment_size: Optional[int] = 120


def get_client_ip(request: Request) -> str:
    """获取客户端真实 IP 地址"""
    # 优先从 X-Forwarded-For 获取（适用于代理/负载均衡器）
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        # X-Forwarded-For 可能包含多个 IP，取第一个
        client_ip = forwarded_for.split(",")[0].strip()
        if client_ip:
            return client_ip
    
    # 其次从 X-Real-IP 获取
    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip.strip()
    
    # 最后从 request.client 获取
    if request.client and request.client.host:
        return request.client.host
    
    # 默认值
    return "0.0.0.0"


def get_auth_header(api_key: str) -> str:
    """生成 Basic Auth 头"""
    credentials = base64.b64encode(f"{api_key}:".encode()).decode()
    return f"Basic {credentials}"


@router.get("/search")
async def search_jobs(
    request: Request,
    keywords: Optional[str] = Query(None, description="搜索关键词"),
    location: Optional[str] = Query("日本", description="搜索地点"),
    locale_code: Optional[str] = Query("ja_JP", description="区域代码"),
    contract_type: Optional[str] = Query(None, description="合同类型"),
    work_hours: Optional[str] = Query(None, description="工作时间"),
    page_size: Optional[int] = Query(20, description="每页结果数"),
    page: Optional[int] = Query(1, description="页码"),
    offset: Optional[int] = Query(0, description="偏移量"),
    radius: Optional[int] = Query(5, description="搜索半径"),
    fragment_size: Optional[int] = Query(120, description="片段大小"),
):
    """
    搜索职位（代理 CareerJet API）

    根据 CAREERJET_MODE 有两种模式：
    - direct: 当前服务直接请求 CareerJet 官方 API（要求本服务出口是静态 IP）
    - proxy: 当前服务把请求转发到专用网关服务，由网关再去请求 CareerJet
    """
    # 获取客户端真实 IP
    client_ip = get_client_ip(request)
    
    # 获取 User-Agent
    user_agent = request.headers.get("User-Agent", "Mogi/Backend/1.0")
    
    # 构建请求参数（两种模式共用）
    params = {
        "locale_code": locale_code,
        "location": location,
        "page_size": page_size,
        "page": page,
        "offset": offset,
        "radius": radius,
        "fragment_size": fragment_size,
        "user_ip": client_ip,
        "user_agent": user_agent,
    }
    
    if keywords:
        params["keywords"] = keywords
    if contract_type:
        params["contract_type"] = contract_type
    if work_hours:
        params["work_hours"] = work_hours

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            # 1) 直接模式：当前服务直接请求 CareerJet 官方 API
            if CAREERJET_MODE == "direct":
                if not CAREERJET_API_KEY:
                    raise HTTPException(
                        status_code=500,
                        detail="CareerJet API Key not configured"
                    )

                headers = {
                    "Authorization": get_auth_header(CAREERJET_API_KEY),
                    "Referer": CAREERJET_REFERER,
                    "User-Agent": user_agent,
                }

                response = await client.get(
                    CAREERJET_API_URL,
                    params=params,
                    headers=headers,
                )
                response.raise_for_status()
                return JSONResponse(content=response.json())

            # 2) 代理模式：转发到专用网关服务，由网关再请求 CareerJet
            if CAREERJET_MODE == "proxy":
                if not CAREERJET_GATEWAY_BASE_URL:
                    raise HTTPException(
                        status_code=500,
                        detail="CareerJet gateway base URL not configured"
                    )

                gateway_url = f"{CAREERJET_GATEWAY_BASE_URL.rstrip('/')}/api/v1/careerjet/search"
                # 把客户端 IP 透传给网关，网关再转给 CareerJet
                gw_headers = {
                    "User-Agent": user_agent,
                    "X-Forwarded-For": client_ip,
                }

                response = await client.get(
                    gateway_url,
                    params=params,
                    headers=gw_headers,
                )
                response.raise_for_status()
                # 直接把网关返回的数据转给前端
                return JSONResponse(content=response.json())

            # 其他未知模式
            raise HTTPException(
                status_code=500,
                detail=f"Invalid CAREERJET_MODE: {CAREERJET_MODE}"
            )
    
    except httpx.HTTPStatusError as e:
        error_data = {}
        try:
            error_data = e.response.json()
        except:
            error_data = {"error": str(e)}
        
        print(f"[CareerJet Proxy] API Error: {error_data}")
        
        status_code = e.response.status_code
        error_msg = error_data.get("error", str(e))
        
        raise HTTPException(
            status_code=status_code,
            detail=f"CareerJet API Error: {error_msg}"
        )
    
    except httpx.RequestError as e:
        print(f"[CareerJet Proxy] Request Error: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Network error: {str(e)}"
        )
    
    except Exception as e:
        print(f"[CareerJet Proxy] Unexpected Error: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"Unexpected error: {str(e)}"
        )


@router.post("/search")
async def search_jobs_post(
    request: Request,
    search_request: CareerJetSearchRequest,
):
    """
    搜索职位（POST 方式，代理 CareerJet API）

    与 GET 版本类似，也支持 direct / proxy 两种模式。
    """
    # 获取客户端真实 IP
    client_ip = get_client_ip(request)
    
    # 获取 User-Agent
    user_agent = request.headers.get("User-Agent", "Mogi/Backend/1.0")
    
    # 构建请求参数
    params = {
        "locale_code": search_request.locale_code or "ja_JP",
        "location": search_request.location or "日本",
        "page_size": search_request.page_size or 20,
        "page": search_request.page or 1,
        "offset": search_request.offset or 0,
        "radius": search_request.radius or 5,
        "fragment_size": search_request.fragment_size or 120,
        "user_ip": client_ip,
        "user_agent": user_agent,
    }
    
    if search_request.keywords:
        params["keywords"] = search_request.keywords
    if search_request.contract_type:
        params["contract_type"] = search_request.contract_type
    if search_request.work_hours:
        params["work_hours"] = search_request.work_hours
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            # 1) 直接模式：当前服务直接请求 CareerJet 官方 API
            if CAREERJET_MODE == "direct":
                if not CAREERJET_API_KEY:
                    raise HTTPException(
                        status_code=500,
                        detail="CareerJet API Key not configured"
                    )

                headers = {
                    "Authorization": get_auth_header(CAREERJET_API_KEY),
                    "Referer": CAREERJET_REFERER,
                    "User-Agent": user_agent,
                }

                response = await client.get(
                    CAREERJET_API_URL,
                    params=params,
                    headers=headers,
                )
                response.raise_for_status()
                return JSONResponse(content=response.json())

            # 2) 代理模式：转发到专用网关服务，由网关再请求 CareerJet
            if CAREERJET_MODE == "proxy":
                if not CAREERJET_GATEWAY_BASE_URL:
                    raise HTTPException(
                        status_code=500,
                        detail="CareerJet gateway base URL not configured"
                    )

                gateway_url = f"{CAREERJET_GATEWAY_BASE_URL.rstrip('/')}/api/v1/careerjet/search"
                gw_headers = {
                    "User-Agent": user_agent,
                    "X-Forwarded-For": client_ip,
                }

                response = await client.post(
                    gateway_url,
                    json=CareerJetSearchRequest(
                        keywords=search_request.keywords,
                        location=search_request.location,
                        locale_code=search_request.locale_code,
                        contract_type=search_request.contract_type,
                        work_hours=search_request.work_hours,
                        page_size=search_request.page_size,
                        page=search_request.page,
                        offset=search_request.offset,
                        radius=search_request.radius,
                        fragment_size=search_request.fragment_size,
                    ).dict(),
                    headers=gw_headers,
                )
                response.raise_for_status()
                return JSONResponse(content=response.json())

            # 其他未知模式
            raise HTTPException(
                status_code=500,
                detail=f"Invalid CAREERJET_MODE: {CAREERJET_MODE}"
            )
    
    except httpx.HTTPStatusError as e:
        error_data = {}
        try:
            error_data = e.response.json()
        except:
            error_data = {"error": str(e)}
        
        print(f"[CareerJet Proxy] API Error: {error_data}")
        
        status_code = e.response.status_code
        error_msg = error_data.get("error", str(e))
        
        raise HTTPException(
            status_code=status_code,
            detail=f"CareerJet API Error: {error_msg}"
        )
    
    except httpx.RequestError as e:
        print(f"[CareerJet Proxy] Request Error: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Network error: {str(e)}"
        )
    
    except Exception as e:
        print(f"[CareerJet Proxy] Unexpected Error: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"Unexpected error: {str(e)}"
        )












