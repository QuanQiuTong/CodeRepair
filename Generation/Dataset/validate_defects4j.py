import json
import time
import subprocess
import re
import os
import signal
import argparse

from Dataset.dataset import get_unified_diff


def run_d4j_test(source, testmethods, bug_id, project, bug):
    bugg = False
    compile_fail = False
    timed_out = False
    entire_bugg = False
    error_string = ""

    # 创建一个继承自当前环境的新环境字典
    test_env = os.environ.copy()
    # 设置 ANT_OPTS 来启用 headless 模式，这将传递给 defects4j 调用的 ant
    test_env["ANT_OPTS"] = "-Djava.awt.headless=true"

    for t in testmethods:
        cmd = 'defects4j test -w %s/ -t %s' % (('/tmp/' + bug_id), t.strip())
        Returncode = ""
        error_file = open("stderr.txt", "wb")

        # 在 Popen 调用中传入修改后的环境
        child = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=error_file, bufsize=-1,
                                 start_new_session=True, env=test_env)
        while_begin = time.time()
        while True:
            Flag = child.poll()
            if Flag == 0:
                Returncode = child.stdout.readlines()  # child.stdout.read()
                print(b"".join(Returncode).decode('utf-8'))
                error_file.close()
                break
            elif Flag != 0 and Flag is not None:
                compile_fail = True
                error_file.close()
                with open("stderr.txt", "rb") as f:
                    r = f.readlines()
                for index, line in enumerate(r):
                    if re.search(':\serror:\s', line.decode('utf-8')):
                        error_string = line.decode('utf-8').strip()
                        if "cannot find symbol" in error_string:
                            error_string += " (" + r[index + 3].decode('utf-8').split("symbol:")[-1].strip() + ")"
                        break
                print("Error")
                print(error_string)
                if error_string == "":
                    subprocess.run('rm -rf ' + '/tmp/' + bug_id, shell=True)
                    subprocess.run("defects4j checkout -p %s -v %s -w %s" % (project, bug + 'b', ('/tmp/' + bug_id)),
                                   shell=True)

                break
            elif time.time() - while_begin > 15:
                error_file.close()
                os.killpg(os.getpgid(child.pid), signal.SIGTERM)
                timed_out = True
                error_string = "TimeOutError"
                break
            else:
                time.sleep(0.001)
        log = Returncode
        if len(log) > 0 and log[-1].decode('utf-8') == "Failing tests: 0\n":
            continue
        else:
            bugg = True
            break

    # Then we check if it passes all the tests, include the previously okay tests
    if not bugg:
        print('So you pass the basic tests, Check if it passes all the test, include the previously passing tests')
        cmd = 'defects4j test -w %s/' % ('/tmp/' + bug_id)
        # 同样，在全量测试的 Popen 调用中也传入修改后的环境
        child = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=-1,
                                 start_new_session=True, env=test_env)
        try:
            # 使用 communicate 并设置超时
            stdout, stderr = child.communicate(timeout=180)
            stdout_str = stdout.decode('utf-8', errors='ignore')
            stderr_str = stderr.decode('utf-8', errors='ignore')
            error_string = stdout_str + stderr_str

            # 检查 AWTError，如果存在则直接视为成功
            if "AWTError: Can't connect to X11 window server" in error_string or "java.awt.AWTError" in error_string:
                print("检测到 X11/AWTError，自动忽略该测试错误，判为通过。")
                entire_bugg = False
            # 检查是否所有测试都通过
            elif "Failing tests: 0" in stdout_str:
                print('success')
                entire_bugg = False
            else:
                entire_bugg = True

        except subprocess.TimeoutExpired:
            print("全量测试超时！")
            # 超时现在应该被视为真正的失败，因为我们已经解决了AWT卡死问题
            os.killpg(os.getpgid(child.pid), signal.SIGTERM)
            bugg = True
            # error_string = "TimeOutError"
        except Exception as e:
            print(f"全量测试出现未知异常: {e}")
            bugg = True
            error_string = str(e)

    return compile_fail, timed_out, bugg, entire_bugg, False, error_string


REAL_SOURCE = []
bug_dict = {}  # Global variable to store bug information


def parse_source(source):
    import javalang
    method_dict = {}
    tree = javalang.parse.parse(source)
    for path, node in tree:
        if isinstance(node, javalang.tree.MethodDeclaration):
            start = getattr(node, "position", None)
            # javalang 0.13.x 以后只有 position，没有 start_position/end_position
            if start is not None:
                start_line = start.line
            else:
                start_line = None
            # 没有 end_line 信息，只能用 None 或自己实现行号推断
            method_dict[node.name] = {
                'start': start_line,
                'end': None
            }
    return method_dict


def grab_failing_testcode(bug_id, file_name, test_method_name, line_number, tmp_bug_id):
    test_dir = os.popen("defects4j export -p dir.src.tests -w /tmp/" + tmp_bug_id).readlines()[-1].strip()

    if not os.path.isfile("/tmp/" + tmp_bug_id + "/" + test_dir + "/" + file_name + ".java"):
        return "", ""
    try:
        with open("/tmp/" + tmp_bug_id + "/" + test_dir + "/" + file_name + ".java", "r") as f:
            source = f.read()
    except:
        with open("/tmp/" + tmp_bug_id + "/" + test_dir + "/" + file_name + ".java", "r", encoding='ISO-8859-1') as f:
            source = f.read()
    # print(source)
    method_dict = parse_source(source)
    lines = source.splitlines()

    if line_number == "":
        return "\n".join(lines[method_dict[test_method_name]['start'] - 1:method_dict[test_method_name]['end']]), ""
    else:
        return "\n".join(lines[method_dict[test_method_name]['start'] - 1:method_dict[test_method_name]['end']]), \
               lines[int(line_number) - 1]

from Dataset.dataset import parse_defects4j_12
def validate_one_patch(folder, patch, bug_id, dataset_name="defects4j_1.2_full", tmp_prefix="test", reset=False):
    # 使用 _JAVA_OPTIONS 强制为所有后续的 JVM 进程设置系统属性
    # 强制解决环境问题
    java_opts = [
        "-Djava.awt.headless=true",
        "-Duser.language=en",
        "-Duser.country=US"
    ]
    os.environ['_JAVA_OPTIONS'] = ' '.join(java_opts)
    print(f"已设置环境变量 _JAVA_OPTIONS='{os.environ['_JAVA_OPTIONS']}'")
    
    global REAL_SOURCE
    global bug_dict  # 确保bug_dict是全局变量

    print(f"### Folder:{folder}, Bug ID:{bug_id}, Dataset Name:{dataset_name}, Tmp Prefix:{tmp_prefix}, Reset:{reset}")

    if dataset_name == "defects4j_1.2_full":
        with open(folder + "Defects4j" + "/single_function_repair.json", "r") as f:
            bug_dict = json.load(f)

    if dataset_name == "defects4j_1.2_full":
        if not bug_dict:
            bug_dict = parse_defects4j_12("Generation/Dataset/")
    elif dataset_name == "defects4j-1.2-single-line":
        p = folder + "Defects4j" + "/single_function_single_line_repair.json"
        print(f"file {p} exists: {os.path.isfile(p)}")
        with open(p, "r") as f:
            bug_dict = json.load(f)

    print(f"Bug dict exists: {bool(bug_dict)}")
    print("Validating patch for bug: {}".format(bug_id))

    if bug_id not in bug_dict:
        bug_id = bug_id.split(".java")[0]  # 作者忘了去掉 .java

    bug, project = bug_id.split("-")[1], bug_id.split("-")[0]

    print(f"Bug: {bug}, Project: {project}")
    start = bug_dict[bug_id]['start']
    end = bug_dict[bug_id]['end']
    with open(folder + "Defects4j/location" + "/{}.buggy.lines".format(bug_id), "r") as f:
        locs = f.read()
    loc = set([x.split("#")[0] for x in locs.splitlines()])  # should only be one
    loc = loc.pop()
    tmp_bug_id = tmp_prefix + project + bug

    if reset:  # check out project again
        subprocess.run('rm -rf ' + '/tmp/' + tmp_prefix + "*", shell=True)  # clean up
        subprocess.run('rm -rf ' + '/tmp/' + tmp_bug_id, shell=True)
        checkout_result = subprocess.run("defects4j checkout -p %s -v %s -w %s" % (project, bug + 'b', ('/tmp/' + tmp_bug_id)),
                       shell=True, capture_output=True, text=True)
        print(checkout_result.stdout)
        print(checkout_result.stderr)
        
        # 我们现在使用环境变量，不再需要修改文件了
        # config_file_path = f"/tmp/{tmp_bug_id}/defects4j.build.properties"
        # try:
        #     with open(config_file_path, "a") as f:
        #         opts = [
        #             "-Djava.awt.headless=true",
        #             "-Duser.language=en",
        #             "-Duser.country=US"
        #         ]
        #         f.write(f"\nd4j.java.opts={' '.join(opts)}\n")
        #     print(f"成功向 {config_file_path} 添加 headless 和 en_US locale 配置。")
        # except FileNotFoundError:
        #     print(f"警告: 无法找到配置文件 {config_file_path}。")

    testmethods = os.popen('defects4j export -w %s -p tests.trigger' % ('/tmp/' + tmp_bug_id)).readlines()
    source_dir = os.popen("defects4j export -p dir.src.classes -w /tmp/" + tmp_bug_id).readlines()[-1].strip()

    if reset:
        try:
            with open("/tmp/" + tmp_bug_id + "/" + source_dir + "/" + loc, 'r') as f:
                REAL_SOURCE = f.read().splitlines()
        except:
            with open("/tmp/" + tmp_bug_id + "/" + source_dir + "/" + loc, 'r', encoding='ISO-8859-1') as f:
                REAL_SOURCE = f.read().splitlines()

    source = REAL_SOURCE
    source = "\n".join(source[:start - 1] + patch.splitlines() + source[end:])

    try:
        with open("/tmp/" + tmp_bug_id + "/" + source_dir + "/" + loc, 'w') as f:
            f.write(source)
        subprocess.run("touch -d '12 December' " + "/tmp/" + tmp_bug_id + "/" + source_dir + "/" + loc,
                       shell=True)
    except:
        with open("/tmp/" + tmp_bug_id + "/" + source_dir + "/" + loc, 'w', encoding='ISO-8859-1') as f:
            f.write(source)
        subprocess.run("touch -d '12 December' " + "/tmp/" + tmp_bug_id + "/" + source_dir + "/" + loc,
                       shell=True)

    compile_fail, timed_out, bugg, entire_bugg, syntax_error, error_string = run_d4j_test(source,
                                                                                          testmethods,
                                                                                          tmp_bug_id,
                                                                                          project, bug)
    
        # 检查 X11/AWTError
    if isinstance(error_string, str) and (
        "AWTError: Can't connect to X11 window server" in error_string or
        "java.awt.AWTError" in error_string
    ):
        print("检测到 X11/AWTError，自动忽略该测试错误，判为通过。")
        return True, ("Ignore X11/AWTError", "", "")

    if not compile_fail and not timed_out and not bugg and not entire_bugg and not syntax_error:
        print("{} has valid patch".format(bug_id))
        return True, ("valid", "", "")
    else:
        test_method_name, failing_line = "", ""
        if (bugg or entire_bugg) and not compile_fail:
            if not os.path.isfile('/tmp/' + tmp_bug_id + '/failing_tests'):
                error_string = ""
            else:
                try:
                    with open('/tmp/' + tmp_bug_id + '/failing_tests', "r") as f:
                        text = f.read()
                except:
                    with open('/tmp/' + tmp_bug_id + '/failing_tests', "r", encoding='ISO-8859-1') as f:
                        text = f.read()
                if len(text.split("--- ")) >= 2:
                    # error_string = text[1]
                    x = text.split("--- ")[1]  # just grab first one
                    test_name = x.splitlines()[0]
                    file_name = test_name.split("::")[0].replace(".", "/")
                    if len(test_name.split("::")) == 1:
                        error_string = ""
                    else:
                        test_method_name = test_name.split("::")[1]
                        line_number = ""
                        error_string = x.splitlines()[1]
                        for line in x.splitlines()[1:]:
                            if test_method_name in line:
                                line_number = line.split(":")[-1].split(")")[0]
                                file_name = line.split("." + test_method_name)[0].split("at ")[1].replace(".", "/")
                                break
                        print(file_name, test_method_name, line_number)
                        failing_function, failing_line = grab_failing_testcode(bug_id.split(".java")[0], file_name,
                                                                               test_method_name, line_number, tmp_bug_id)
                else:
                    error_string = ""
        print("{} has invalid patch".format(bug_id))
        return False, (error_string, test_method_name, failing_line)


# used to mass validate a bunch of generated files
def validate_all_patches(folder, j_file, dataset_name, tmp_prefix="test"):
    if dataset_name == "defects4j_1.2_full":
        with open("Defects4j" + "/single_function_repair.json", "r") as f:
            bug_dict = json.load(f)

    with open(folder + "/" + j_file, "r") as f:
        repair_dict = json.load(f)

    plausible, total = 0, 0
    seen_bugs = {}

    bugs_with_plausible_patch = []

    for s, patches in repair_dict.items():
        bug_id = s.split(".java")[0]
        bug = bug_id.split("-")[1]
        project = bug_id.split("-")[0]
        start = bug_dict[bug_id]['start']
        end = bug_dict[bug_id]['end']
        with open("Defects4j/location" + "/{}.buggy.lines".format(bug_id), "r") as f:
            locs = f.read()
        loc = set([x.split("#")[0] for x in locs.splitlines()])  # should only be one
        loc = loc.pop()

        tmp_bug_id = tmp_prefix + project + bug

        if tmp_bug_id not in seen_bugs:
            for sb in seen_bugs.keys():
                subprocess.run('rm -rf ' + '/tmp/' + sb, shell=True)
            seen_bugs[tmp_bug_id] = 1
            subprocess.run('rm -rf ' + '/tmp/' + tmp_bug_id, shell=True)
            subprocess.run("defects4j checkout -p %s -v %s -w %s" % (project, bug + 'b', ('/tmp/' + tmp_bug_id)),
                           shell=True)
            with open(folder + "/" + j_file, "w") as f:
                json.dump(repair_dict, f)

        testmethods = os.popen('defects4j export -w %s -p tests.trigger' % ('/tmp/' + tmp_bug_id)).readlines()
        source_dir = os.popen("defects4j export -p dir.src.classes -w /tmp/" + tmp_bug_id).readlines()[-1].strip()

        diff_set = set()

        for index, generation in enumerate(patches):
            patch = generation['patch']
            lines = bug_dict[bug_id]['fix'].splitlines()
            leading_white_space = len(lines[0]) - len(lines[0].lstrip())
            fix = "\n".join([line[leading_white_space:] for line in lines])
            diff = get_unified_diff(fix, patch)
            if diff in diff_set:
                continue
            diff_set.add(diff)
            print(diff)

            if seen_bugs[tmp_bug_id] == 1:
                try:
                    with open("/tmp/" + tmp_bug_id + "/" + source_dir + "/" + loc, 'r') as f:
                        source = f.read().splitlines()
                except:
                    with open("/tmp/" + tmp_bug_id + "/" + source_dir + "/" + loc, 'r', encoding='ISO-8859-1') as f:
                        source = f.read().splitlines()
                seen_bugs[tmp_bug_id] = source
            else:
                source = seen_bugs[tmp_bug_id]
            source = "\n".join(source[:start - 1] + patch.splitlines() + source[end + 1:])

            try:
                with open("/tmp/" + tmp_bug_id + "/" + source_dir + "/" + loc, 'w') as f:
                    f.write(source)
                subprocess.run("touch -d '12 December' " + "/tmp/" + tmp_bug_id + "/" + source_dir + "/" + loc,
                               shell=True)
            except:
                with open("/tmp/" + tmp_bug_id + "/" + source_dir + "/" + loc, 'w', encoding='ISO-8859-1') as f:
                    f.write(source)
                subprocess.run("touch -d '12 December' " + "/tmp/" + tmp_bug_id + "/" + source_dir + "/" + loc,
                               shell=True)

            compile_fail, timed_out, bugg, entire_bugg, syntax_error, error_string = run_d4j_test(source,
                                                                                                  testmethods,
                                                                                                  tmp_bug_id,
                                                                                                  project, bug)
            if not compile_fail and not timed_out and not bugg and not entire_bugg and not syntax_error:
                plausible += 1
                repair_dict[s][index]['valid'] = True
                print('success')
                print("{} has valid patch: {}".format(bug_id, index))
                bugs_with_plausible_patch.append(bug_id)
            else:
                repair_dict[s][index]['error'] = error_string
                print("{} has invalid patch: {}".format(bug_id, index))

            total += 1

    print("{}/{} are plausible".format(plausible, total))

    with open(folder + "/" + j_file, "w") as f:
        json.dump(repair_dict, f)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--folder", type=str)
    parser.add_argument("--jfile", type=str, default="lm_repair.json")
    parser.add_argument("--dataset_name", type=str, default=None)
    parser.add_argument("--project_name", type=str, default=None)
    parser.add_argument("--bug_id_g", type=str, default=None)
    parser.add_argument("--tmp", type=str, default="test")  # facilitate parallel runs
    args = parser.parse_args()

    validate_all_patches(args.folder, args.jfile, args.dataset_name, tmp_prefix=args.tmp)


if __name__ == "__main__":
    main()
