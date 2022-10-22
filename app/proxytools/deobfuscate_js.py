import base64
import re

#
# Javascript string expression deobfuscator.
# Author: neskk
#


def mapchar(match):
    # print(f'map "{match.group(1)}" to char code {match.group(2)}{match.group(3)}')
    parts = match.group(1).split(',')
    charlist = []
    for charcode in parts:
        res = int(charcode)

        if match.group(2) == '-':
            res -= int(match.group(3))
        elif match.group(2) == '+':
            res += int(match.group(3))

        # convert char code to char
        charlist.append(chr(res))

    # check if additional array manipulation is done
    if match.group(4) == ".reverse()":
        charlist.reverse()

    return '"' + ''.join(charlist) + '"'


def atob(match):
    # print(f'atob for {match.group(1)}')
    return '"' + base64.b64decode(match.group(1)).decode("utf-8") + '"'


def reverse(match):
    # print(f'reverse "{match.group(1)}"')
    res = [*match.group(1)]
    res.reverse()
    return '"' + ''.join(res) + '"'


def add(match):
    # print(f'add {match.group(1)} to {match.group(2)}')
    return str(int(match.group(1)) + int(match.group(2)))


def subtract(match):
    # print(f'subtract {match.group(2)} from {match.group(1)}')
    return str(int(match.group(1)) - int(match.group(2)))


def repeat(match):
    # print(f'repeat "{match.group(1)}", {match.group(2)} times')
    return '"' + match.group(1) * int(match.group(2)) + '"'


def substring(match):
    # print(f'"{match.group(1)}".substring({match.group(2)})')
    res = match.group(1)
    limits = match.group(2).split(',')

    start_idx = int(limits[0])
    end_idx = None
    if len(limits) == 2:
        end_idx = int(limits[1])

    return '"' + res[start_idx:end_idx] + '"'


def concat(match):
    # print(f'concatenate "{match.group(1)}" to "{match.group(2)}"')
    return '"' + match.group(1) + match.group(2) + '"'


def deobfuscate_js(script):
    script = re.sub(r'\[(.*?)\]\.map\(\(code\).*?\(code([\+\-])?(\d)?\)\)(\.reverse\(\))?\.join\(\"\"\)', mapchar, script)
    script = re.sub(r'atob\(\"(.*?)\"\)', atob, script)
    script = re.sub(r'\"([\.\d]*)\"\.split\(\"\"\)\.reverse\(\)\.join\(\"\"\)', reverse, script)
    script = re.sub(r'(\d+)\+(\d+)', add, script)
    script = re.sub(r'(\d+)\-(\d+)', subtract, script)
    script = re.sub(r'\"([\.\d]*)\"\.repeat\((\d+)\)', repeat, script)
    script = re.sub(r'\"([\.\d]*)\"\.substring\((.*?)\)', substring, script)

    while 'concat' in script:
        script = re.sub(r'\"([\.\d]*)\"\.concat\(\"([\.\d]*)\"\)', concat, script)

    ip = re.sub(r'\"([\.\d]+)\"', r'\1', script)
    return ip
