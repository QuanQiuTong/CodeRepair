# Generation/util/qwen_request.py
import os

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

# ../../Qwen3-1.7B
DEFAULT_QWEN_MODEL_PATH = "/home/quanqiutong/Projects/Qwen3-1.7B" # os.path.abspath("../../Qwen3-1.7B")

_qwen_model = None
_qwen_tokenizer = None

def load_qwen_model(model_path):
    global _qwen_model, _qwen_tokenizer
    if _qwen_model is None or _qwen_tokenizer is None:
        print(f"Loading Qwen model from {model_path} ...")
        _qwen_tokenizer = AutoTokenizer.from_pretrained(model_path, trust_remote_code=True)
        _qwen_model = AutoModelForCausalLM.from_pretrained(model_path, device_map='auto', trust_remote_code=True)
        print("Qwen model loaded.")

def request_qwen_engine(config, model_path=DEFAULT_QWEN_MODEL_PATH):
    global _qwen_model, _qwen_tokenizer
    if _qwen_model is None or _qwen_tokenizer is None:
        load_qwen_model(model_path)
    # 假设config["messages"]是openai风格的chat消息
    prompt = _qwen_tokenizer.apply_chat_template(
        config["messages"], tokenize=False, add_generation_prompt=True
    )
    print("\n-----[Qwen Prompt]-----\n" + prompt + "\n---------------\n")
    inputs = _qwen_tokenizer([prompt], return_tensors="pt").to(_qwen_model.device)
    outputs = _qwen_model.generate(
        inputs.input_ids,
        max_new_tokens=config.get("max_tokens", 512) + 100,  # 思维链太长了
        temperature=config.get("temperature", 0.7)
    )
    generated = outputs[:, inputs.input_ids.shape[-1]:]
    response = _qwen_tokenizer.decode(generated[0], skip_special_tokens=True)
    print("\n-----[Qwen Raw Output]-----\n" + response + "\n---------------\n")

    # 从原始响应中提取代码块
    extracted_code = response
    if "```" in response:
        # 假设代码在第一个 ``` 块中
        parts = response.split("```")
        if len(parts) > 1:
            # 提取代码块内容，并移除可能的语言标识符（如 java）
            code_content = parts[1]
            if code_content.startswith("java\n"):
                code_content = code_content[5:]
            elif code_content.startswith("java"):
                 code_content = code_content[4:]
            extracted_code = "```java\n" + code_content + "\n```"

    return {
        "choices": [{"message": {"content": extracted_code}}],
        "usage": {
            "prompt_tokens": inputs.input_ids.shape[-1],
            "completion_tokens": generated.shape[-1],
            "total_tokens": inputs.input_ids.shape[-1] + generated.shape[-1]
        }
    }

# 优化后的 Qwen 系统提示
CONCISE_QWEN_SYSTEM_PROMPT = """You are an expert Automated Program Repair tool.
Your goal is to fix the buggy code with a single line replacement.
Analyze the user's request, which includes the code, the buggy line, and the test failure.
Think step-by-step but be concise.
1. Briefly state the root cause of the error.
2. Provide the single correct line of code to fix the bug inside a Java code block.
Do not repeat the problem description. Be direct and focus on the solution."""