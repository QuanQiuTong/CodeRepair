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


# 要求回答简洁
SYSTEM_MESSAGE = "You are an expert Automated Program Repair tool. " \
                 "Your task is to fix a buggy line of code. " \
                 "Provide only the single correct line of code as the fix. " \
                 "Do not explain. Do not add any text other than the code."

SYSTEM_MESSAGE_QWEN = "你是一个负责修复代码缺陷的专家。"\
    "你的任务是修复一行有缺陷的代码。请仅提供单行正确的代码作为修复，不要解释，也不要添加任何其他文本。"

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
                          system_message: str = SYSTEM_MESSAGE_QWEN,
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

RESP = r"""{
    "id": "chatcmpl-Br5YKYkrBlKjxJyyVnVPrLBJdfUUs",
    "object": "chat.completion",
    "created": 1751992428,
    "model": "gpt-4o-mini-2024-07-18",
    "choices": [
        {
            "index": 0,
            "message": {
                "role": "assistant",
                "content": "Here is the corrected line that should be placed at the infill location:\n\n```java\nif (dataset == null) {\n```\n\n",
                "refusal": null,
                "annotations": []
            },
            "logprobs": null,
            "finish_reason": "length"
        }
    ],
    "usage": {
        "prompt_tokens": 358,
        "completion_tokens": 100,
        "total_tokens": 458,
        "prompt_tokens_details": {
            "cached_tokens": 0,
            "audio_tokens": 0
        },
        "completion_tokens_details": {
            "reasoning_tokens": 0,
            "audio_tokens": 0,
            "accepted_prediction_tokens": 0,
            "rejected_prediction_tokens": 0
        }
    },
    "system_fingerprint": "fp_efad92c60b"
}"""

def request_chatgpt_engine(config):
    # 返回一个模拟的响应以便于测试
    # input("回车以继续请求 ChatGPT 引擎...")  # 用于调试时暂停执行
    # return json.loads(RESP)

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
            with open("chatgpt_engine_response.json", "a", encoding="utf-8") as f:  # 改为追加模式
                f.write(json.dumps(response.json(), indent=4))
            return response.json()
        except requests.exceptions.RequestException as e:
            print("API request error:", e)
            time.sleep(5)  # 等待重试


def request_engine(config):
    # 返回一个模拟的响应以便于测试
    # return json.loads(RESP)

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
            with open("engine_response.json", "a", encoding="utf-8") as f:  # 改为追加模式
                f.write(json.dumps(response.json(), indent=4))
            return response.json()
        except requests.exceptions.RequestException as e:
            print("API request error:", e)
            time.sleep(5)  # 等待重试
