import openai
import os
import signal
import time
import requests
import json

from prompt import INIT_CHATGPT_INFILL_PROMPT, INIT_CHATGPT_CORRECT_RESPONSE, \
    INIT_CHATGPT_INFILL_FAILING_TEST_LINE, INIT_CHATGPT_INFILL_HUNK_FAILING_TEST_LINE, \
    INIT_CHATGPT_CORRECT_HUNK_RESPONSE, INIT_CHATGPT_INFILL_FUNCTION_FAILING_TEST_LINE, \
    INIT_CHATGPT_CORRECT_FUNCTION_RESPONSE, INIT_CHATGPT_INFILL_FUNCTION_FAILING_QUIXBUGS, \
    INIT_CHATGPT_INFILL_LINE_FAILING_TEST_LINE_QUIXBUGS, INIT_CHATGPT_INFILL_HUNK_FAILING_TEST_LINE_QUIXBUGS
from prompt import CHATGPT_LOCALIZE_PROMPT, CHATGPT_LOCALIZE_RESPONSE
from util.util import get_initial_failing_tests, build_values


def create_openai_config(prompt,
                         engine_name="code-davinci-002",
                         stop="# Provide a fix for the buggy function",
                         max_tokens=3000,
                         top_p=0.95,
                         temperature=1):
    return {
        "engine": engine_name,
        "prompt": prompt,
        "max_tokens": max_tokens,
        "top_p": top_p,
        "temperature": temperature,
        "logprobs": 1,
        "stop": stop
    }


# 修改 create_chatgpt_config 函数以支持 DeerAPI 的请求格式
def create_chatgpt_config(prev: dict, message: str, max_tokens: int, bug_id, bugs, few_shot: int = 0,
                          temperature: float = 1, # default most diverse temperature
                          system_message: str = "You are an Automated Program Repair tool.",
                          localize: bool = False,
                          hunk: bool = False,
                          function: bool =False,
                          dataset: str = ""):
    if prev == {}:
        if few_shot > 0:
            config = {
                "model": "gpt-4o-mini",
                "max_tokens": max_tokens,
                "temperature": temperature,
                "messages": [
                    {"role": "system", "content": system_message}
                ]
            }
            bug_project = bug_id.split("-")[0]
            examples = []
            for bug, v in bugs.items():
                if (bug.startswith(bug_project) and bug != bug_id) or ("quixbugs" in dataset and bug != bug_id):
                    x = v
                    x['name'] = bug
                    examples.append(x)
            examples = sorted(examples, key=lambda d: len(d['buggy']))
            for e in examples[:few_shot]:
                if localize:
                    config["messages"].append({"role": "user", "content": CHATGPT_LOCALIZE_PROMPT.format(
                        buggy_code=e['buggy'],
                        root_cause=get_initial_failing_tests(None, e['name'])
                    )})
                    config["messages"].append({"role": "assistant", "content": CHATGPT_LOCALIZE_RESPONSE.format(
                        buggy_line=e['buggy_line']
                    ).strip()})
                elif hunk:
                    pass  # 省略其他逻辑
                elif function:
                    pass  # 省略其他逻辑
                else:
                    pass  # 省略其他逻辑
            config["messages"].append({"role": "user", "content": message.strip()})
            return config
        else:
            return {
                "model": "gpt-4o-mini",
                "max_tokens": max_tokens,
                "temperature": temperature,
                "messages": [
                    {"role": "system", "content": system_message},
                    {"role": "user", "content": message.strip()}
                ]
            }
    else:
        return prev


def handler(signum, frame):
    raise Exception("end of time")


# 修改 request_chatgpt_engine 函数以将 API 回复写入文件

def request_chatgpt_engine(config):
    url = "https://api.deerapi.com/v1/chat/completions"
    headers = {
        'Accept': 'application/json',
        'Authorization': 'sk-rXdg1my1TGhx9DPVKVy6qxaYUUOQpdqykBvsWsSJuUNo9iQq',
        'User-Agent': 'DeerAPI/1.0.0 (https://api.deerapi.com)',
        'Content-Type': 'application/json'
    }
    payload = json.dumps(config)
    response = None
    while response is None:
        try:
            response = requests.post(url, headers=headers, data=payload)
            response.raise_for_status()
            with open("chatgpt_engine_response.json", "w", encoding="utf-8") as f:
                f.write(response.text)
            return response.json()
        except requests.exceptions.RequestException as e:
            print("API request error:", e)
            time.sleep(5)  # 等待重试


# 修改 request_engine 函数以将 API 回复写入文件

def request_engine(config):
    url = "https://api.deerapi.com/v1/completions"
    headers = {
        'Accept': 'application/json',
        'Authorization': 'sk-rXdg1my1TGhx9DPVKVy6qxaYUUOQpdqykBvsWsSJuUNo9iQq',
        'User-Agent': 'DeerAPI/1.0.0 (https://api.deerapi.com)',
        'Content-Type': 'application/json'
    }
    payload = json.dumps(config)
    response = None
    while response is None:
        try:
            response = requests.post(url, headers=headers, data=payload)
            response.raise_for_status()
            with open("engine_response.json", "w", encoding="utf-8") as f:
                f.write(response.text)
            return response.json()
        except requests.exceptions.RequestException as e:
            print("API request error:", e)
            time.sleep(5)  # 等待重试
