import os

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

# ../../Qwen3-1.7B
DEFAULT_QWEN_MODEL_PATH = os.path.abspath("../Qwen3-4B")
# DEFAULT_QWEN_MODEL_PATH = "/home/quanqiutong/Projects/Qwen3-1.7B"

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
    
    prompt = _qwen_tokenizer.apply_chat_template(
        config["messages"], tokenize=False, add_generation_prompt=True
    )
    print("\n-----[above is Qwen prompt]-----\n")

    inputs = _qwen_tokenizer([prompt], return_tensors="pt").to(_qwen_model.device)
    
    outputs = _qwen_model.generate(
        inputs.input_ids,
        
        # 1. 大幅降低 temperature，减少随机性，使其输出更稳定、更具确定性
        temperature=1.1, # config.get("temperature", 1.0), 

        # 2. 增加 repetition_penalty，惩罚重复的token，有效避免无限循环
        repetition_penalty=1.1,
        # 3. max_new_tokens 可以适当减小，因为我们期望直接得到代码，而不是长篇大论
        max_new_tokens=config.get("max_tokens", 256), # 150(来自config) + a buffer
        # 4. 使用 top_p 进行核采样，是比temperature更推荐的控制多样性的方式
        top_p=0.9,
    )
    
    generated = outputs[:, inputs.input_ids.shape[-1]:]
    response = _qwen_tokenizer.decode(generated[0], skip_special_tokens=True)
    print("\n-----[Qwen Raw Output]-----\n" + response + "\n---------------\n")

    # 从原始响应中提取代码块，并移除思维链
    extracted_code = response
    # 优先移除 <think> 标签
    if "<think>" in extracted_code:
        # 假设 <think> ... </think> 之后是代码
        think_end_index = extracted_code.rfind("</think>")
        if think_end_index != -1:
            extracted_code = extracted_code[think_end_index + len("</think>"):]

    if "```" in extracted_code:
        # 假设代码在第一个 ``` 块中
        parts = extracted_code.split("```")
        if len(parts) > 1:
            # 提取代码块内容，并移除可能的语言标识符（如 java）
            code_content = parts[1].strip() # 使用 strip() 清理空白
            if code_content.startswith("java"):
                code_content = '\n'.join(code_content.split('\n')[1:])
            
            # 返回一个干净的、只包含代码块的字符串
            extracted_code = "```java\n" + code_content + "\n```"
    else:
        # 如果没有代码块，可能模型只生成了代码行
        extracted_code = response.strip()


    # 包装成OpenAI格式返回
    return {
        "choices": [{"message": {"content": extracted_code}}],
        "usage": {
            "prompt_tokens": inputs.input_ids.shape[-1],
            "completion_tokens": generated.shape[-1],
            "total_tokens": inputs.input_ids.shape[-1] + generated.shape[-1]
        }
    }