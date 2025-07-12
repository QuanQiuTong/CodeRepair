from util.util import build_values

def build_prompt_zh(args, v):
    INFILL_TOKEN=">>> [ INFILL ] <<<"
    if args.failing_test:
        prompt = INIT_QWEN_INFILL_FAILING_TEST.format(
            buggy_code=(v['prefix'] + "\n" + INFILL_TOKEN + "\n" + v['suffix']),
            buggy_hunk=v['buggy_line'],
            failing_test=v['failing_tests'][0]['test_method_name'],
            error_message=v['failing_tests'][0]['failure_message'].strip())
    elif args.assertion_line:
        if args.hunk:
            if "defects4j" in args.dataset:
                prompt = INIT_QWEN_INFILL_HUNK_FAILING_TEST_LINE.format(
                    buggy_code=(v['prefix'] + "\n" + INFILL_TOKEN + "\n" + v['suffix']),
                    buggy_hunk=v['buggy_line'],
                    failing_test=v['failing_tests'][0]['test_method_name'],
                    error_message=v['failing_tests'][0]['failure_message'].strip(),
                    failing_line=v['failing_tests'][0]['failing_line'].strip())
            else:
                prompt = INIT_QWEN_INFILL_HUNK_FAILING_TEST_LINE_QUIXBUGS.format(
                    buggy_code=(v['prefix'] + "\n" + INFILL_TOKEN + "\n" + v['suffix']),
                    buggy_hunk=v['buggy_line'],
                    function_header=v['function_header'],
                    values=build_values(v['failing_tests']['input_values']),
                    return_val=v['failing_tests']['output_values'])
        else:
            if "defects4j" in args.dataset:
                prompt = INIT_QWEN_INFILL_FAILING_TEST_LINE.format(
                    buggy_code=(v['prefix'] + "\n" + INFILL_TOKEN + "\n" + v['suffix']),
                    buggy_hunk=v['buggy_line'],
                    failing_test=v['failing_tests'][0]['test_method_name'],
                    error_message=v['failing_tests'][0]['failure_message'].strip(),
                    failing_line=v['failing_tests'][0]['failing_line'].strip())
            else:
                prompt = INIT_QWEN_INFILL_LINE_FAILING_TEST_LINE_QUIXBUGS.format(
                    buggy_code=(v['prefix'] + "\n" + INFILL_TOKEN + "\n" + v['suffix']),
                    buggy_hunk=v['buggy_line'],
                    function_header=v['function_header'],
                    values=build_values(v['failing_tests']['input_values']),
                    return_val=v['failing_tests']['output_values'])
    elif args.failing_test_method:
        failing_function = v['failing_tests'][0]['failing_function'].splitlines()
        leading_white_space = len(failing_function[0]) - len(failing_function[0].lstrip())
        failing_function = "\n".join([line[leading_white_space:] for line in failing_function])
        prompt = INIT_QWEN_INFILL_FAILING_TEST_METHOD.format(
            buggy_code=(v['prefix'] + "\n" + INFILL_TOKEN + "\n" + v['suffix']),
            buggy_hunk=v['buggy_line'],
            failing_test_method=failing_function,
            error_message=v['failing_tests'][0]['failure_message'].strip())
    else:
        if args.hunk:
            prompt = INIT_QWEN_INFILL_HUNK.format(
                buggy_code=(v['prefix'] + "\n" + INFILL_TOKEN + "\n" + v['suffix']),
                buggy_hunk=v['buggy_line'])
        else:
            prompt = INIT_QWEN_INFILL_PROMPT.format(
                buggy_code=(v['prefix'] + "\n" + INFILL_TOKEN + "\n" + v['suffix']),
                buggy_hunk=v['buggy_line'])
    return prompt

INIT_PROMPT = """
以下代码存在缺陷。
{buggy_code}

请提供修复后的版本。
{function_header}
"""

INIT_QWEN_PROMPT = """
以下代码存在缺陷。
```
{buggy_code}
```
请提供修复后的版本。
"""

INIT_QWEN_INFILL_PFC_PROMPT = """
以下代码包含一个已被移除的有缺陷代码块。
```
{buggy_code}
```
这是在补全位置被移除的原始有缺陷代码块
```
// 有缺陷代码块
{buggy_hunk}
```
该代码在此测试用例失败: `{failing_test}()`
在此测试行: `{failing_line}`
报错信息: {error_message}

可以通过以下代码块修复
1.
```
{fix_hunk}
```
"""

PFC_SUFFIX_PROMPT = "请在补全位置生成一个备选的修复代码块。"

PFC_ADD_PROMPT = """
{num}.
```
{fix_hunk}
```
"""

INIT_QWEN_INFILL_LINE_PFC_PROMPT = """
以下代码包含一个已被移除的有缺陷代码行。
```
{buggy_code}
```
这是在补全位置被移除的原始有缺陷代码行
```
// 有缺陷代码行
{buggy_hunk}
```
该代码在此测试用例失败: `{failing_test}()`
在此测试行: `{failing_line}`
报错信息: {error_message}

可以通过以下代码块修复
1.
```
{fix_hunk}
```
"""

PFC_SUFFIX_LINE_PROMPT = "请在补全位置生成一个备选的修复代码行。"

INIT_QWEN_FUNCTION_PFC_PROMPT = """
以下代码包含一个缺陷。
```
{buggy_code}
```
该代码在此测试用例失败: `{failing_test}()`
在此测试行: `{failing_line}`
报错信息: {error_message}

可以通过以下补丁函数修复
```
{patch_function}
```
"""

PFC_SUFFIX_FUNCTION_PROMPT = "请生成一个备选的修复函数。"

INIT_QWEN_INFILL_PROMPT = """
以下代码包含一个已被移除的有缺陷代码行。
```
{buggy_code}
```
这是在补全位置被移除的原始有缺陷代码行
```
// 有缺陷代码行
{buggy_hunk}
```

请在补全位置提供正确的代码行。
"""

INIT_QWEN_INFILL_FAILING_TEST = """
以下代码包含一个已被移除的有缺陷代码行。
```
{buggy_code}
```
这是在补全位置被移除的原始有缺陷代码行
```
// 有缺陷代码行
{buggy_hunk}
```
该代码在此测试用例失败: `{failing_test}()`
报错信息: {error_message}

请在补全位置提供正确的代码行。
"""

INIT_QWEN_INFILL_FAILING_TEST_LINE = """
以下代码包含一个已被移除的有缺陷代码行。
```
{buggy_code}
```
这是在补全位置被移除的原始有缺陷代码行
```
// 有缺陷代码行
{buggy_hunk}
```
该代码在此测试用例失败: `{failing_test}()`
在此测试行: `{failing_line}`
报错信息: {error_message}

请在补全位置提供正确的代码行。
"""

INIT_QWEN_INFILL_HUNK = """
以下代码包含一个已被移除的有缺陷代码块。
```
{buggy_code}
```
这是在补全位置被移除的原始有缺陷代码块
```
// 有缺陷代码块
{buggy_hunk}
```

请在补全位置提供正确的代码块。
"""


INIT_QWEN_INFILL_HUNK_FAILING_TEST_LINE = """
以下代码包含一个已被移除的有缺陷代码块。
```
{buggy_code}
```
这是在补全位置被移除的原始有缺陷代码块
```
// 有缺陷代码块
{buggy_hunk}
```
该代码在此测试用例失败: `{failing_test}()`
在此测试行: `{failing_line}`
报错信息: {error_message}

请在补全位置提供正确的代码块。
"""

INIT_QWEN_INFILL_LINE_FAILING_TEST_LINE_QUIXBUGS = """
以下代码包含一个已被移除的有缺陷代码行。
```
{buggy_code}
```
这是在补全位置被移除的原始有缺陷代码行
```
// 有缺陷代码行
{buggy_hunk}
```
{function_header}({values}) 错误地返回了 {return_val} 

请在补全位置提供正确的代码行。
"""

INIT_QWEN_INFILL_HUNK_FAILING_TEST_LINE_QUIXBUGS = """
以下代码包含一个已被移除的有缺陷代码块。
```
{buggy_code}
```
这是在补全位置被移除的原始有缺陷代码块
```
// 有缺陷代码块
{buggy_hunk}
```
{function_header}({values}) 错误地返回了 {return_val} 

请在补全位置提供正确的代码块。
"""


INIT_QWEN_INFILL_FUNCTION_FAILING_TEST_LINE = """
以下代码包含一个缺陷。
```
{buggy_code}
```
该代码在此测试用例失败: `{failing_test}()`
在此测试行: `{failing_line}`
报错信息: {error_message}

请提供修复该缺陷的正确函数。
"""

INIT_QWEN_INFILL_FUNCTION_FAILING_QUIXBUGS= """
以下代码包含一个缺陷。
```
{buggy_code}
```
{function_header}({values}) 错误地返回了 {return_val} 

请提供修复该缺陷的正确函数。
"""

INIT_QWEN_INFILL_FUNCTION = """
以下代码包含一个缺陷。
```
{buggy_code}
```

请提供修复该缺陷的正确函数。
"""

INIT_QWEN_INFILL_FAILING_TEST_METHOD = """
以下代码包含一个已被移除的有缺陷代码行。
```
{buggy_code}
```
这是在补全位置被移除的原始有缺陷代码行
```
// 有缺陷代码行
{buggy_hunk}
```
该代码在此测试用例失败: 
```
{failing_test_method}
```
报错信息: {error_message}

请在补全位置提供正确的代码行。
"""


INIT_QWEN_CORRECT_RESPONSE = """
补全位置的正确代码行为
```
{correct_hunk}
```
"""

INIT_QWEN_CORRECT_HUNK_RESPONSE = """
补全位置的正确代码块为
```
{correct_hunk}
```
"""

INIT_QWEN_CORRECT_FUNCTION_RESPONSE = """
正确的函数为
```
{correct_hunk}
```
"""

QWEN_LOCALIZE_PROMPT = """
以下代码包含一个有缺陷的代码行。
```
{buggy_code}
```

以下测试用例未通过：
{root_cause}

请指出哪一行代码有缺陷。
"""

QWEN_LOCALIZE_RESPONSE = """
上述代码中的有缺陷代码行为
```
{buggy_line}
```
"""
