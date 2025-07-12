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

    # --- 定义停止词 ---
    # 新增 </think> 作为停止词，可以在模型完成思考后立即停止，防止其继续输出
    stop_words = ["```", "<|im_end|>", "</think>", "user :"] 
    # 使用列表推导式来处理可能的多token停止词
    stop_token_ids = [tid for word in stop_words for tid in _qwen_tokenizer.encode(word, add_special_tokens=False)]
    # Transformers的StoppingCriteria需要一个二维列表，但eos_token_id是一维的。这里的实现是正确的。

    inputs = _qwen_tokenizer([prompt], return_tensors="pt").to(_qwen_model.device)
    
    outputs = _qwen_model.generate(
        inputs.input_ids,
        # 1. 大幅降低 temperature，减少随机性，使其输出更稳定、更具确定性
        temperature=config.get("temperature", 0.4), 
        # 2. 增加 repetition_penalty，惩罚重复的token，有效避免无限循环
        repetition_penalty=1.1,
        # 3. max_new_tokens 可以适当减小，因为我们期望直接得到代码，而不是长篇大论
        max_new_tokens=config.get("max_tokens", 256), # 150(来自config) + a buffer
        # 4. 使用 top_p 进行核采样，是比temperature更推荐的控制多样性的方式
        top_p=0.9,
        # 5. 应用停止词ID
        eos_token_id=stop_token_ids 
    )
    
    generated = outputs[:, inputs.input_ids.shape[-1]:]
    response = _qwen_tokenizer.decode(generated[0], skip_special_tokens=True)
    print("\n-----[Qwen Raw Output]-----\n" + response + "\n---------------\n")

    # ... (后处理逻辑基本不变，但可以简化) ...
    
    # 简化后的后处理逻辑
    final_code = ""
    # 优先从代码块中提取
    if "```" in response:
        # 使用正则表达式更稳健地提取
        import re
        match = re.search(r"```(?:java)?\n(.*?)\n```", response, re.DOTALL)
        if match:
            final_code = match.group(1).strip()
    
    # 如果没有找到代码块，或者提取失败，则认为整个响应是代码（作为后备方案）
    if not final_code:
        # 移除可能残留的思维链标签
        think_end_index = response.rfind("</think>")
        if think_end_index != -1:
            final_code = response[think_end_index + len("</think>"):].strip()
        else:
            final_code = response.strip()

    # 包装成OpenAI格式返回
    return {
        "choices": [{"message": {"content": f"```java\n{final_code}\n```"}}],
        "usage": {
            "prompt_tokens": inputs.input_ids.shape[-1],
            "completion_tokens": generated.shape[-1],
            "total_tokens": inputs.input_ids.shape[-1] + generated.shape[-1]
        }
    }