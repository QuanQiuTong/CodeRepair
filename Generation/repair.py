import argparse
import json
import os

import openai

from Dataset.dataset import parse_defects4j_12, parse_defects4j_2
from Dataset.dataset import parse_python, parse_java, get_unified_diff
from prompt import INIT_PROMPT, INIT_CHATGPT_PROMPT, INIT_CHATGPT_INFILL_PROMPT
from prompt import INIT_CHATGPT_INFILL_FAILING_TEST, INIT_CHATGPT_INFILL_FAILING_TEST_LINE, \
    INIT_CHATGPT_INFILL_FAILING_TEST_METHOD, INIT_CHATGPT_INFILL_HUNK_FAILING_TEST_LINE, \
    INIT_CHATGPT_INFILL_FUNCTION_FAILING_TEST_LINE, INIT_CHATGPT_INFILL_HUNK, INIT_CHATGPT_INFILL_FUNCTION, \
    INIT_CHATGPT_INFILL_FUNCTION_FAILING_QUIXBUGS, INIT_CHATGPT_INFILL_LINE_FAILING_TEST_LINE_QUIXBUGS, \
    INIT_CHATGPT_INFILL_HUNK_FAILING_TEST_LINE_QUIXBUGS
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


ATTACHED_PROMPT = "\nProvide the fix only, with the least thinking.\n" \
                    "The fix should be a single line wrapped in \n```\ncode block\n```\n"

def build_prompt(args, v):
    INFILL_TOKEN=">>> [ INFILL ] <<<"
    if args.failing_test:
        prompt = INIT_CHATGPT_INFILL_FAILING_TEST.format(
            buggy_code=(v['prefix'] + "\n" + INFILL_TOKEN + "\n" + v['suffix']),
            buggy_hunk=v['buggy_line'],
            failing_test=v['failing_tests'][0]['test_method_name'],
            error_message=v['failing_tests'][0]['failure_message'].strip())
    elif args.assertion_line:
        if args.hunk:
            if "defects4j" in args.dataset:
                prompt = INIT_CHATGPT_INFILL_HUNK_FAILING_TEST_LINE.format(
                    buggy_code=(v['prefix'] + "\n" + INFILL_TOKEN + "\n" + v['suffix']),
                    buggy_hunk=v['buggy_line'],
                    failing_test=v['failing_tests'][0]['test_method_name'],
                    error_message=v['failing_tests'][0]['failure_message'].strip(),
                    failing_line=v['failing_tests'][0]['failing_line'].strip())
            else:
                prompt = INIT_CHATGPT_INFILL_HUNK_FAILING_TEST_LINE_QUIXBUGS.format(
                    buggy_code=(v['prefix'] + "\n" + INFILL_TOKEN + "\n" + v['suffix']),
                    buggy_hunk=v['buggy_line'],
                    function_header=v['function_header'],
                    values=build_values(v['failing_tests']['input_values']),
                    return_val=v['failing_tests']['output_values'])
        else:
            if "defects4j" in args.dataset:
                prompt = INIT_CHATGPT_INFILL_FAILING_TEST_LINE.format(
                    buggy_code=(v['prefix'] + "\n" + INFILL_TOKEN + "\n" + v['suffix']),
                    buggy_hunk=v['buggy_line'],
                    failing_test=v['failing_tests'][0]['test_method_name'],
                    error_message=v['failing_tests'][0]['failure_message'].strip(),
                    failing_line=v['failing_tests'][0]['failing_line'].strip())
            else:
                prompt = INIT_CHATGPT_INFILL_LINE_FAILING_TEST_LINE_QUIXBUGS.format(
                    buggy_code=(v['prefix'] + "\n" + INFILL_TOKEN + "\n" + v['suffix']),
                    buggy_hunk=v['buggy_line'],
                    function_header=v['function_header'],
                    values=build_values(v['failing_tests']['input_values']),
                    return_val=v['failing_tests']['output_values'])
    elif args.failing_test_method:
        failing_function = v['failing_tests'][0]['failing_function'].splitlines()
        leading_white_space = len(failing_function[0]) - len(failing_function[0].lstrip())
        failing_function = "\n".join([line[leading_white_space:] for line in failing_function])
        prompt = INIT_CHATGPT_INFILL_FAILING_TEST_METHOD.format(
            buggy_code=(v['prefix'] + "\n" + INFILL_TOKEN + "\n" + v['suffix']),
            buggy_hunk=v['buggy_line'],
            failing_test_method=failing_function,
            error_message=v['failing_tests'][0]['failure_message'].strip())
    else:
        if args.hunk:
            prompt = INIT_CHATGPT_INFILL_HUNK.format(
                buggy_code=(v['prefix'] + "\n" + INFILL_TOKEN + "\n" + v['suffix']),
                buggy_hunk=v['buggy_line'])
        else:
            prompt = INIT_CHATGPT_INFILL_PROMPT.format(
                buggy_code=(v['prefix'] + "\n" + INFILL_TOKEN + "\n" + v['suffix']),
                buggy_hunk=v['buggy_line'])

def chatgpt_apr_infill(args, bugs):
    print(len(bugs))
    if args.hunk:
        max_tokens = 200 # + 200 # for CoT
    else:
        max_tokens = 100 # + 200 # for CoT
    results = {}
    # with open(os.path.join(args.folder, "lm_repair.json"), "r") as f:
    #     results = json.load(f)
    #
    # found = False

    for bug, v in bugs.items():
        print("---- {} ----".format(bug))
        if "suffix" not in v or (not args.hunk and bug == "subsequences"):
            continue
        # if bug != "Mockito-1.java" and found is False:
        #     continue
        # found = True
        # if bug in results:
        #     continue

        base_prompt = build_prompt(args, v)

        # "Be brief, do not repeat the problem description, just provide the fix. Wrap the fix in a \n```\ncode block\n```"
        prompt = base_prompt + ATTACHED_PROMPT

        config = create_chatgpt_config(prev={}, message=prompt, max_tokens=max_tokens,
                                       bug_id=bug, bugs=bugs, few_shot=args.few_shot, hunk=args.hunk, dataset=args.dataset)
        if num_tokens_from_messages(config["messages"]) + max_tokens > 4096:
            continue

        results[bug] = []
        generations = {}
        tries = 0
        true_valid, reset = False, True
        while tries < args.total_tries and not true_valid:
            history = {}
            prompt_times = 0
            repeated_bad = False

            while prompt_times < args.chain_length:
                config = create_chatgpt_config(prev=history, message=prompt, max_tokens=max_tokens,
                                               bug_id=bug, bugs=bugs, few_shot=args.few_shot, hunk=args.hunk,
                                               dataset=args.dataset)
                if num_tokens_from_messages(config["messages"]) + max_tokens > 4096:
                    break
                for message in config['messages']:
                    print("{} : {}".format(message['role'], message['content']))
                ret = my_request(config)

                # 统计并打印输出 token 数量
                completion_tokens = ret['usage']['completion_tokens']
                print(f"Tries: {tries + 1} | Output Tokens: {completion_tokens}")

                tries += 1
                # print(ret["choices"][0]['message'])
                func, pre_history = complex_chatgpt_parse(ret["choices"][0]['message']["content"],
                                                          suffix=v['suffix'],
                                                          prefix=v['prefix'])
                print("Tries: {} Tokens: {}".format(tries, num_tokens_from_messages(config["messages"])))
                if func != "":
                    if "quixbugs-python" in args.dataset:
                        output = v['prefix'] + "\n" + v['leading_whitespace'] + func.strip() + "\n" + v['suffix']
                    else:
                        output = v['prefix'] + "\n" + func.strip() + "\n" + v['suffix']
                    print(get_unified_diff(v['buggy'], output))
                    if output not in generations:
                        if args.lang == "java":
                            valid, error_message = write_file(args, args.folder, output,
                                                              bug.split(".java")[0] + "_{}.java".format(
                                                                  len(generations)),
                                                              bug.split(".java")[0], skip_val=False, lang=args.lang,
                                                              reset=reset)
                        else:
                            valid, error_message = write_file(args, args.folder, output,
                                                              bug.split(".py")[0] + "_{}.py".format(
                                                                  len(generations)),
                                                              bug.split(".py")[0], skip_val=False, lang=args.lang,
                                                              reset=reset)
                        generations[output] = error_message
                        if reset:
                            reset = False
                    else:
                        valid = False
                        error_message = generations[output]
                    results[bug].append(
                        {'patch': func, 'valid': valid, "prompt": config, "prompt_times": prompt_times,
                         'tries': tries, "usage": ret['usage'], "error": error_message, 'output': ret})
                    if valid:
                        true_valid = True
                        break

                    history = config
                    # 注意：这里的 pre_history 是经过 qwen_request.py 清理后的，不含 <think>
                    history["messages"].append({"role": "assistant", "content": pre_history}) 
                    
                    # 生成基础的错误信息
                    response = build_error_message_based_chatgpt_response_message(args, error_message, v, args.hunk)
                    
                    # 加入明确的负面约束，告诉模型哪个 patch 失败了
                    failed_patch = func.strip()
                    response += f"\nYour previous attempt was:\n```java\n{failed_patch}\n```\nThis was incorrect. Do not generate this line again."

                    # 在反馈消息后追加关键指令，以保持输出简洁
                    response += ATTACHED_PROMPT
                    
                    history["messages"].append({"role": "user", "content": response})
                    prompt_times += 1
                    repeated_bad = False
                else:
                    if repeated_bad:  # to address multiple bad outputs ending up here causing issue
                        break
                    repeated_bad = True

        with open(os.path.join(args.folder, "lm_repair.json"), "w") as f:
            json.dump(results, f)


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
