import csv
import os
import json
import yaml
import asyncio
import datetime
import logging
import logging.handlers
import colorlog
from typing import Dict, List, Optional
from openai import AsyncOpenAI
from pydantic import BaseModel
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

# 配置文件路径
config_file = 'data/config.yaml'

# 读取配置
with open(config_file, 'r', encoding='utf-8') as f:
    config = yaml.safe_load(f)

# 配置文件修改时间
config_mtime = os.path.getmtime(config_file)

# 初始化日志系统
def setup_logging():
    # 获取日志配置
    log_config = config['logging']
    log_level = getattr(logging, log_config['level'].upper())
    log_file = log_config['file']
    max_size = log_config['max_size'] * 1024 * 1024  # 转换为字节
    backup_count = log_config['backup_count']
    
    # 创建日志目录
    log_dir = os.path.dirname(log_file)
    if log_dir and not os.path.exists(log_dir):
        os.makedirs(log_dir)
    
    logger = logging.getLogger()
    logger.setLevel(log_level)
    
    # 清除现有处理器
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
    
    # --- 1. 文本文件处理器 (保持简洁，无颜色码) ---
    file_handler = logging.handlers.RotatingFileHandler(
        log_file,
        maxBytes=max_size,
        backupCount=backup_count,
        encoding='utf-8'
    )
    file_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    file_handler.setFormatter(file_formatter)
    
    # --- 2. 彩色控制台处理器 ---
    console_handler = logging.StreamHandler()
    
    # 定义颜色方案
    color_formatter = colorlog.ColoredFormatter(
        "%(log_color)s%(asctime)s - %(levelname)-8s%(reset)s %(white)s%(message)s",
        datefmt='%Y-%m-%d %H:%M:%S',
        reset=True,
        log_colors={
            'DEBUG':    'cyan',
            'INFO':     'green',
            'WARNING':  'yellow',
            'ERROR':    'red',
            'CRITICAL': 'red,bg_white',
        },
        secondary_log_colors={},
        style='%'
    )
    console_handler.setFormatter(color_formatter)
    
    # 添加处理器
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    
    return logger

# 初始化日志
logger = setup_logging()

# 定义 lifespan 事件处理器
@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动时执行初始化加载IP访问记录
    await load_ip_accesses()
    logger.info("服务启动完成")
    
    try:
        yield
    finally:
        # 关闭时执行保存IP访问记录（添加超时保护）
        try:
            await asyncio.wait_for(save_ip_accesses(), timeout=3.0)
            logger.info("服务关闭完成")
        except asyncio.TimeoutError:
            logger.warning("保存IP访问记录超时，跳过保存")
        except Exception as e:
            logger.error(f"保存IP访问记录失败: {str(e)}")


# 初始化FastAPI应用
app = FastAPI(lifespan=lifespan)

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

# 检查并重载配置
async def check_config_reload():
    global config, config_mtime, client, logger
    
    try:
        current_mtime = os.path.getmtime(config_file)
        if current_mtime > config_mtime:
            # 配置文件已修改，重新加载
            with open(config_file, 'r', encoding='utf-8') as f:
                new_config = yaml.safe_load(f)
            
            # 更新配置
            config = new_config
            config_mtime = current_mtime
            
            # 更新OpenAI客户端
            client = AsyncOpenAI(
                api_key=config['model']['api_key'],
                base_url=config['model']['base_url']
            )
            
            # 重新配置日志
            logger = setup_logging()
            logger.info(f"配置文件已重载: {datetime.datetime.now()}")
    except Exception as e:
        logger.error(f"重载配置失败: {str(e)}")

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

# 获取真实客户端IP
def get_real_ip(request: Request) -> str:
    """
    从请求头中获取真实客户端IP
    优先从 X-Forwarded-For 获取，如果没有则使用 request.client.host
    """
    # 从 X-Forwarded-For 头获取IP
    x_forwarded_for = request.headers.get('X-Forwarded-For')
    if x_forwarded_for:
        # X-Forwarded-For 格式: "client_ip, proxy1_ip, proxy2_ip, ..."
        # 取第一个IP（最原始的客户端IP）
        real_ip = x_forwarded_for.split(',')[0].strip()
        if real_ip:
            return real_ip
    
    # 如果没有 X-Forwarded-For，使用默认的客户端IP
    return request.client.host

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
        logger.info(f"IP计数重置 - IP: {ip}, 时间窗口: {time_window}秒")
        return True
    
    # 检查是否超过限制
    if access.count >= config['security']['ip_limit']['max_requests']:
        # 阻塞IP
        block_time = config['security']['ip_limit']['block_time']
        access.blocked_until = now + datetime.timedelta(minutes=block_time)
        logger.warning(f"IP访问超限被阻塞 - IP: {ip}, 当前计数: {access.count}, 阻塞时间: {block_time}分钟")
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

# 处理聊天请求
@app.post("/", response_model=ChatResponse)
async def chat(request: Request, chat_request: ChatRequest):
    # 检查配置是否需要重载
    await check_config_reload()
    
    # 获取客户端真实IP
    client_ip = get_real_ip(request)
    nickname = chat_request.user_nickname
    
    logger.info(f"收到请求 - 真实IP: {client_ip}, CDN IP: {request.client.host}, 昵称: {nickname}")
    
    # 检查IP是否被阻塞
    if await check_ip_blocked(client_ip):
        block_time = config['security']['ip_limit']['block_time']
        logger.warning(f"IP被阻塞 - IP: {client_ip}, 昵称: {nickname}, 阻塞时间: {block_time}分钟")
        raise HTTPException(status_code=429, detail=f"请求过快，请{block_time}分钟后再试喵")
    
    # 更新IP访问记录（在检查之前更新）
    if client_ip not in ip_accesses:
        ip_accesses[client_ip] = IPAccess(client_ip)
        logger.info(f"新IP首次访问 - IP: {client_ip}, 昵称: {nickname}")
    else:
        access = ip_accesses[client_ip]
        access.last_access = datetime.datetime.now()
        access.count += 1
        logger.info(f"IP访问计数更新 - IP: {client_ip}, 昵称: {nickname}, 当前计数: {access.count}")
    
    # 检查IP访问次数
    if not await check_ip_limit(client_ip):
        block_time = config['security']['ip_limit']['block_time']
        logger.warning(f"IP访问超限 - IP: {client_ip}, 昵称: {nickname}, 阻塞时间: {block_time}分钟")
        raise HTTPException(status_code=429, detail=f"请求过快，请{block_time}分钟后再试喵")
    
    # 检查输入长度
    if not await check_input_length(nickname):
        logger.warning(f"输入长度超限 - IP: {client_ip}, 昵称: {nickname}, 长度: {len(nickname)}")
        raise HTTPException(status_code=400, detail=f"输入长度超过限制，最大{config['security']['input_limit']['max_chars']}字符")
    
    # 检查违禁词
    if not await check_badwords(nickname):
        logger.warning(f"包含违禁词 - IP: {client_ip}, 昵称: {nickname}")
        raise HTTPException(status_code=400, detail="输入包含违禁词，拒绝处理喵")
    
    # 保存IP访问记录
    await save_ip_accesses()
    
    logger.info(f"开始处理请求 - IP: {client_ip}, 昵称: {nickname}")
    
    # 替换昵称占位符
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
        try:
            # 提取JSON部分
            if '```json' in assistant_response:
                json_str = assistant_response.split('```json')[1].split('```')[0]
            else:
                json_str = assistant_response
            
            # 解析JSON
            parsed_response = json.loads(json_str.strip())
            
            logger.info(f"请求处理成功 - IP: {client_ip}, 昵称: {nickname}, 相似度: {parsed_response.get('Strinova-similarity', 'N/A')}, AI锐评: {parsed_response.get('reason', 'N/A')}")
            
            return ChatResponse(response=parsed_response)
        except json.JSONDecodeError as e:
            logger.error(f"AI返回格式错误 - IP: {client_ip}, 昵称: {nickname}, 错误: {str(e)}")
            raise HTTPException(status_code=500, detail=f"AI返回格式错误: {str(e)}")
    except Exception as e:
        logger.error(f"API调用失败 - IP: {client_ip}, 昵称: {nickname}, 错误: {str(e)}")
        raise HTTPException(status_code=500, detail=f"API调用失败: {str(e)}")

# 根路径
@app.get("/")
async def root():
    # 检查配置是否需要重载
    await check_config_reload()
    return {"message":"Server is running.  卡拉彼丘计算服务正在运行喵！"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host=config['server']['host'],
        port=config['server']['port'],
        reload=False
    )
