import argparse
import json
import os

import openai

from Dataset.dataset import parse_defects4j_12, parse_defects4j_2
from Dataset.dataset import parse_python, parse_java, get_unified_diff
from prompt import INIT_PROMPT, INIT_CHATGPT_INFILL_FUNCTION_FAILING_TEST_LINE, INIT_CHATGPT_INFILL_FUNCTION, \
    INIT_CHATGPT_INFILL_FUNCTION_FAILING_QUIXBUGS
from prompt import build_prompt_en
from prompt_zh import build_prompt_zh

from util.api_request import create_chatgpt_config, request_chatgpt_engine
from util.api_request import create_openai_config, request_engine
from util.qwen_request import request_qwen_engine
from util.util import simple_chatgpt_parse, complex_chatgpt_parse, num_tokens_from_messages
from util.util import write_file, build_error_message_based_chatgpt_response_message, build_values

ROOT = os.path.dirname(os.path.abspath(__file__))
my_request = request_qwen_engine

def load_length(lang="python"):
    if lang == "python":
        with open(ROOT+"/codex_token_length.json", "r") as f:
            length = json.load(f)
    else:
        with open(ROOT+"/codex_token_length_java.json", "r") as f:
            length = json.load(f)
    return length

ATTACHED_PROMPT = "\nVERY IMPORTANT: Your final answer must be ONLY the single line of corrected Java code inside a code block. Do not provide any explanation, preamble, or thinking process. Your entire response should be in the format ```java\n[CODE]\n```."

def _build_dynamic_prompt(base_prompt, failed_patches):
    """将历史失败记录追加到基础Prompt后，构建用于当次请求的完整Prompt。"""
    current_prompt = base_prompt
    if failed_patches:
        failed_patches_str = ""
        for i, p in enumerate(failed_patches):
            # 移除可能存在的代码块标记，只保留纯代码
            p_clean = p.replace("```java", "").replace("```", "").strip()
            failed_patches_str += f"{i + 1}. ```java\n{p_clean}\n```\n"
        
        current_prompt += "\n\nThe following attempts have failed. Do not generate them again:\n"
        current_prompt += failed_patches_str
    
    current_prompt += ATTACHED_PROMPT
    return current_prompt

def chatgpt_apr_infill(args, bugs):
    """主修复函数，使用“带记忆的单次请求”策略。"""
    print(len(bugs))
    max_tokens = 150  # 为单行修复提供足够的空间
    results = {}

    for bug, v in bugs.items():
        print("---- {} ----".format(bug))
        if "suffix" not in v or (not args.hunk and bug == "subsequences"):
            continue

        base_prompt = build_prompt_zh(args, v) if args.engine == "qwen" else build_prompt_en(args, v)

        failed_patches = []
        generations = {}
        results[bug] = []
        is_fixed = False
        
        consecutive_failures = 0
        MAX_CONSECUTIVE_FAILURES = 5 # 设置一个阈值

        for tries in range(args.total_tries):
            if is_fixed:
                break

            print(f"Tries: {tries + 1}/{args.total_tries}")
            
            # 1. 动态构建带所有失败历史的Prompt
            current_prompt = _build_dynamic_prompt(base_prompt, failed_patches)
            
            # 2. 每次都创建全新的、无历史记录的config
            config = create_chatgpt_config(prev={}, message=current_prompt, max_tokens=max_tokens,
                                           bug_id=bug, bugs=bugs, few_shot=args.few_shot, hunk=args.hunk,
                                           dataset=args.dataset)

            if num_tokens_from_messages(config["messages"]) + max_tokens > 4096:
                print("Prompt is too long, skipping.")
                break

            for message in config['messages']:
                print("{} : {}".format(message['role'], message['content']))
            
            ret = my_request(config)
            
            completion_tokens = ret['usage']['completion_tokens']
            print(f"Output Tokens: {completion_tokens}")

            patch, _ = complex_chatgpt_parse(ret["choices"][0]['message']["content"],
                                             suffix=v['suffix'],
                                             prefix=v['prefix'])
            
            if not patch or not patch.strip():
                print("Generated an empty patch. Trying again.")
                continue

            patch_content = patch.strip()
            
            # 3. 检查是否重复生成了已知的失败补丁
            if patch_content in failed_patches:
                print("Generated a repeated failed patch. Trying again.")
                continue

            # 在检查patch是否为空或重复后
            if not patch or not patch.strip() or patch_content in failed_patches:
                print("Generated an empty or repeated failed patch. Trying again.")
                consecutive_failures += 1
                if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                    print(f"Failed {MAX_CONSECUTIVE_FAILURES} consecutive times. Breaking loop for this bug.")
                    break # 跳出当前bug的修复循环
                continue
            else:
                # 如果成功生成了新补丁，重置计数器
                consecutive_failures = 0

            if "quixbugs-python" in args.dataset:
                output = v['prefix'] + "\n" + v['leading_whitespace'] + patch_content + "\n" + v['suffix']
            else:
                output = v['prefix'] + "\n" + patch_content + "\n" + v['suffix']
            
            print(get_unified_diff(v['buggy'], output))

            if output in generations:
                is_valid = False
                error_message = generations[output]
            else:
                if args.lang == "java":
                    is_valid, error_message = write_file(args, args.folder, output,
                                                      bug.split(".java")[0] + "_{}.java".format(len(generations)),
                                                      bug.split(".java")[0], skip_val=False, lang=args.lang,
                                                      reset=(tries == 0))
                else: # python
                    is_valid, error_message = write_file(args, args.folder, output,
                                                      bug.split(".py")[0] + "_{}.py".format(len(generations)),
                                                      bug.split(".py")[0], skip_val=False, lang=args.lang,
                                                      reset=(tries == 0))
                generations[output] = error_message

            results[bug].append({
                'patch': patch_content, 'valid': is_valid, "prompt": config,
                'tries': tries + 1, "usage": ret['usage'], 
                "error": error_message, 'output': ret
            })
            
            if is_valid:
                print(f"Bug {bug} fixed successfully!")
                is_fixed = True
            else:
                # 4. 将新的失败补丁加入“黑名单”
                if patch_content not in failed_patches:
                    failed_patches.append(patch_content)

        with open(os.path.join(args.folder, "lm_repair.json"), "w") as f:
            json.dump(results, f, indent=2)



def chatgpt_apr(args, bugs):
    results = {}
    with open(os.path.join(args.folder, "lm_repair.json"), "r") as f:
        results = json.load(f)
    found = False

    for bug, v in bugs.items():
        print("---- {} ----".format(bug))
        found = False
        if bug not in results or len(results[bug]) == 0:
            continue
        for p in results[bug]:
            if p['valid']:
                found = True
        print(found)
        if found:
            continue
        # if bug != "shortest_path_length" and found is False:
        #     continue
        # found = True
        generations = {}
        starting_length = len(results[bug])
        # results[bug] = []
        tries = results[bug][-1]['tries']
        # tries = 0
        true_valid, reset = False, True
        max_tries = args.total_tries
        while tries < max_tries and not true_valid:
            if args.assertion_line:
                if "defects4j" in args.dataset:
                    prompt = INIT_CHATGPT_INFILL_FUNCTION_FAILING_TEST_LINE.format(buggy_code=v['buggy'],
                                                                                   failing_test=v['failing_tests'][0]['test_method_name'],
                                                                                   error_message=v['failing_tests'][0]['failure_message'].strip(),
                                                                                   failing_line=v['failing_tests'][0]['failing_line'].strip())
                else:
                    prompt = INIT_CHATGPT_INFILL_FUNCTION_FAILING_QUIXBUGS.format(buggy_code=v['buggy'],
                                                                                  function_header=v['function_header'],
                                                                                  values=build_values(v['failing_tests']['input_values']),
                                                                                  return_val=v['failing_tests']['output_values'])
            else:
                prompt = INIT_CHATGPT_INFILL_FUNCTION.format(buggy_code=v['buggy'])
            fake_message = [{"role": "system", "content": v['buggy']}]
            max_tokens = int(num_tokens_from_messages(fake_message) * 3)
            config = create_chatgpt_config(prev={}, message=prompt, max_tokens=max_tokens,
                                           bug_id=bug, bugs=bugs, few_shot=args.few_shot, function=True, dataset=args.dataset)
            if num_tokens_from_messages(config['messages']) + max_tokens > 4096:
                break
            if num_tokens_from_messages(config['messages']) > 1000:
                max_tries = 50
            history = {}
            prompt_times = 0
            while prompt_times < args.chain_length:
                config = create_chatgpt_config(prev=history, message=prompt, max_tokens=max_tokens,
                                               bug_id=bug, bugs=bugs, few_shot=args.few_shot, function=True, dataset=args.dataset)
                if num_tokens_from_messages(config['messages']) + max_tokens > 4096:
                    break
                for message in config['messages']:
                    print("{} : {}".format(message['role'], message['content']))
                ret = my_request(config)
                tries += 1
                func, pre_history = simple_chatgpt_parse(ret["choices"][0]['message']["content"])
                print("Tries: {} Tokens: {}".format(tries, num_tokens_from_messages(config["messages"])))
                if func != "":
                    print(get_unified_diff(v['buggy'], func))
                    if func not in generations:
                        args.lang = args.lang.lower()
                        if args.lang == "java":
                            valid, error_message = write_file(args, args.folder, func,
                                                  bug.split(".java")[0] + "_{}.java".format(
                                                      len(generations)+starting_length),
                                                  bug.split(".java")[0], skip_val=False, lang=args.lang,
                                                  reset=reset)
                        else:
                            valid, error_message = write_file(args, args.folder, func,
                                                              bug.split(".py")[0] + "_{}.py".format(
                                                                  len(generations)),
                                                              bug.split(".py")[0], skip_val=False, lang=args.lang,
                                                              reset=reset)
                        generations[func] = error_message
                        if reset:
                            reset = False
                    else:
                        valid = False
                        error_message = generations[func]
                    results[bug].append({'patch': func, 'valid': valid, "prompt": config, "prompt_times": prompt_times,
                                         'tries': tries, "usage": ret['usage'], "error": error_message, 'output': ret})
                    if valid:
                        true_valid = True
                        break

                    history = config
                    history["messages"].append({"role": "assistant", "content": pre_history})
                    response = build_error_message_based_chatgpt_response_message(args, error_message, v, args.hunk, True)
                    history["messages"].append({"role": "user", "content": response})
                prompt_times += 1

        with open(os.path.join(args.folder, "lm_repair.json"), "w") as f:
            json.dump(results, f)


def get_token_length():
    length = {}
    bugs = parse_java("./")
    for bug, v in bugs.items():
        print("---- {} ----".format(bug))
        prompt = INIT_PROMPT.format(buggy_code=v['buggy'], function_header=v['function_header'])
        config = create_openai_config(prompt, max_tokens=50)
        ret = request_engine(config)
        print(ret["usage"]["prompt_tokens"])
        length[bug] = ret["usage"]["prompt_tokens"]

    with open("codex_token_length_java.json", "w") as f:
        json.dump(length, f)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--folder", type=str, default="Results/test")
    parser.add_argument("--lang", type=str, default="python")
    parser.add_argument("--dataset", type=str, default="quixbugs-python")
    parser.add_argument("--chatgpt", action="store_true")
    parser.add_argument("--few_shot", type=int, default=0)
    parser.add_argument("--chain_length", type=int, default=3)
    parser.add_argument("--total_tries", type=int, default=50)
    parser.add_argument("--suffix", action="store_true")
    parser.add_argument("--failing_test", action="store_true")
    parser.add_argument("--assertion_line", action="store_true")
    parser.add_argument("--failing_test_method", action="store_true")
    parser.add_argument("--hunk", action="store_true")
    parser.add_argument("--tmp_prefix", type=str, default="test")
    parser.add_argument("--key_file", type=str, default="api_key.txt")
    parser.add_argument("--engine", type=str, default="qwen", help="Engine to use: chatgpt or qwen")
    args = parser.parse_args()

    global my_request
    if args.engine == "qwen":
        my_request = request_qwen_engine
        global ATTACHED_PROMPT
        ATTACHED_PROMPT = "\n非常重要：最终答案必须仅包含一个代码块内的单行修正Java代码。不要提供任何解释、前言或思考过程。你的整个回答应为以下格式：```java\n[CODE]\n```。"
    else:
        my_request = request_chatgpt_engine

    openai.api_key = open(args.key_file, 'r').read().strip()
    os.makedirs(args.folder, exist_ok=True)
    with open(os.path.join(args.folder, "args.txt"), "w") as f:
        f.write(str(args))

    if args.dataset == "quixbugs-python":
        bugs = parse_python(ROOT+"/")
    elif args.dataset == "quixbugs-java":
        bugs = parse_java(ROOT+"/")
    elif args.dataset == "defects4j-1.2-function":
        bugs = parse_defects4j_12(ROOT+"/Dataset/")
    elif args.dataset == "defects4j-1.2-single-hunk":
        bugs = parse_defects4j_12(ROOT+"/Dataset/", single_hunk=True)
    elif args.dataset == "defects4j-1.2-single-line":
        bugs = parse_defects4j_12(ROOT+"/Dataset/", single_line=True)
    elif args.dataset == "defects4j-2.0-single-line":
        bugs = parse_defects4j_2(ROOT+"/Dataset/")
    else:
        raise NotImplementedError

    if args.suffix:
        chatgpt_apr_infill(args, bugs)
    else:
        chatgpt_apr(args, bugs)


if __name__ == "__main__":
    main()
