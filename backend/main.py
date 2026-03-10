import asyncio
import csv
import datetime
import os
from typing import Dict, List, Optional

import yaml
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from openai import AsyncOpenAI
from pydantic import BaseModel

# 读取配置
with open('data/config.yaml', 'r', encoding='utf-8') as f:
    config = yaml.safe_load(f)

# 初始化FastAPI应用
app = FastAPI()

# 配置CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 在生产环境中应该设置具体的前端地址
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 初始化OpenAI客户端
client = AsyncOpenAI(
    api_key=config['model']['api_key'],
    base_url=config['model']['base_url']
)

# IP访问记录
class IPAccess:
    def __init__(self, ip: str):
        self.ip = ip
        self.first_access = datetime.datetime.now()
        self.last_access = self.first_access
        self.count = 1
        self.blocked_until = None

ip_accesses: Dict[str, IPAccess] = {}

# 输入请求模型
class ChatRequest(BaseModel):
    user_nickname: str

# 输出响应模型
class ChatResponse(BaseModel):
    response: dict

# 检查IP是否被阻塞
async def check_ip_blocked(ip: str) -> bool:
    access = ip_accesses.get(ip)
    if access and access.blocked_until:
        if datetime.datetime.now() < access.blocked_until:
            return True
        else:
            # 阻塞时间已过，解除阻塞
            access.blocked_until = None
    return False

# 检查IP访问次数
async def check_ip_limit(ip: str) -> bool:
    if not config['security']['ip_limit']['enabled']:
        return True
    
    access = ip_accesses.get(ip)
    if not access:
        return True
    
    # 检查是否在时间窗口内
    time_window = config['security']['ip_limit']['time_window']
    now = datetime.datetime.now()
    time_diff = (now - access.last_access).total_seconds()
    
    # 如果超过时间窗口，重置计数
    if time_diff > time_window:
        access.count = 1
        access.last_access = now
        return True
    
    # 检查是否超过限制
    if access.count >= config['security']['ip_limit']['max_requests']:
        # 阻塞IP
        block_time = config['security']['ip_limit']['block_time']
        access.blocked_until = now + datetime.timedelta(minutes=block_time)
        return False
    
    return True

# 检查输入长度
async def check_input_length(message: str) -> bool:
    max_chars = config['security']['input_limit']['max_chars']
    return len(message) <= max_chars

# 检查违禁词
async def check_badwords(message: str) -> bool:
    if not config['security']['badwords']['enabled']:
        return True
    
    badwords_file = config['security']['badwords']['file_path']
    if not os.path.exists(badwords_file):
        return True
    
    with open(badwords_file, 'r', encoding='utf-8') as f:
        badwords = [line.strip() for line in f if line.strip()]
    
    for word in badwords:
        if word in message:
            return False
    return True

# 保存IP访问记录到CSV
async def save_ip_accesses():
    with open('data/ip_accesses.csv', 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['IP', '首次访问日期', '最后访问日期', '次数'])
        for access in ip_accesses.values():
            writer.writerow([
                access.ip,
                access.first_access.strftime('%Y-%m-%d %H:%M:%S'),
                access.last_access.strftime('%Y-%m-%d %H:%M:%S'),
                access.count
            ])

# 加载IP访问记录
async def load_ip_accesses():
    global ip_accesses
    if os.path.exists('data/ip_accesses.csv'):
        with open('data/ip_accesses.csv', 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                access = IPAccess(row['IP'])
                access.first_access = datetime.datetime.strptime(row['首次访问日期'], '%Y-%m-%d %H:%M:%S')
                access.last_access = datetime.datetime.strptime(row['最后访问日期'], '%Y-%m-%d %H:%M:%S')
                access.count = int(row['次数'])
                ip_accesses[row['IP']] = access

# 初始化加载IP访问记录
@app.on_event("startup")
async def startup_event():
    await load_ip_accesses()

# 关闭时保存IP访问记录
@app.on_event("shutdown")
async def shutdown_event():
    await save_ip_accesses()

# 处理聊天请求
@app.post("/", response_model=ChatResponse)
async def chat(request: Request, chat_request: ChatRequest):
    # 获取客户端IP
    client_ip = request.client.host
    
    # 检查IP是否被阻塞
    if await check_ip_blocked(client_ip):
        raise HTTPException(status_code=429, detail="请求过快，请10分钟后再试")
    
    # 检查IP访问次数
    if not await check_ip_limit(client_ip):
        raise HTTPException(status_code=429, detail="请求过快，请10分钟后再试")
    
    # 检查输入长度
    if not await check_input_length(chat_request.user_nickname):
        raise HTTPException(status_code=400, detail=f"输入长度超过限制，最大{config['security']['input_limit']['max_chars']}字符")
    
    # 检查违禁词
    if not await check_badwords(chat_request.user_nickname):
        raise HTTPException(status_code=400, detail="输入包含违禁词，拒绝处理")
    
    # 更新IP访问记录
    if client_ip not in ip_accesses:
        ip_accesses[client_ip] = IPAccess(client_ip)
    else:
        access = ip_accesses[client_ip]
        access.last_access = datetime.datetime.now()
        access.count += 1
    
    # 保存IP访问记录
    await save_ip_accesses()
    
    # 替换昵称占位符
    nickname = chat_request.user_nickname
    system_prompt = config['model']['system_prompt']
    user_prompt = config['model']['user_prompt'].replace("{{nickname}}", nickname)
    
    # 调用OpenAI API
    try:
        response = await client.chat.completions.create(
            model=config['model']['model'],
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ]
        )
        
        # 提取响应内容
        assistant_response = response.choices[0].message.content
        
        # 解析JSON响应
        import json
        try:
            # 提取JSON部分
            if '```json' in assistant_response:
                json_str = assistant_response.split('```json')[1].split('```')[0]
            else:
                json_str = assistant_response
            
            # 解析JSON
            parsed_response = json.loads(json_str.strip())
            return ChatResponse(response=parsed_response)
        except json.JSONDecodeError as e:
            raise HTTPException(status_code=500, detail=f"AI返回格式错误: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"API调用失败: {str(e)}")

# 根路径
@app.get("/")
async def root():
    return {"message":"Server is running.  卡拉彼丘计算服务正在运行喵！"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host=config['server']['host'],
        port=config['server']['port'],
        reload=True
    )
