import re
with open('index.html', 'r', encoding='utf-8') as f:
    content = f.read()
m = re.search(r'<script>(.*?)</script>', content, re.DOTALL)
if m:
    js = m.group(1)
    opens = js.count('(') + js.count('{') + js.count('[')
    closes = js.count(')') + js.count('}') + js.count(']')
    print(f'Opens: {opens}, Closes: {closes}, Diff: {opens - closes}')
    print(f'(={js.count(chr(40))} )={js.count(chr(41))}  brace_open={js.count(chr(123))} brace_close={js.count(chr(125))}  [{js.count(chr(91))}]={js.count(chr(93))}')
    # Find position of unmatched
    stack = []
    for i, ch in enumerate(js):
        if ch in '({[':
            stack.append((ch, i))
        elif ch in ')}]':
            if not stack:
                print(f'Extra closing {ch} at position {i}')
            else:
                stack.pop()
    if stack:
        for ch, i in stack:
            print(f'Unmatched {ch} at position {i}')
            start = max(0, i-100)
            end = min(len(js), i+100)
            print(f'  Context: ...{js[start:end]}...')
            # Show surrounding characters with markers
            before = js[max(0,i-20):i]
            after = js[i:min(len(js),i+20)]
            print(f'  Before: |{before}|')
            print(f'  At:     |{after}|')
    else:
        print('All brackets matched!')
else:
    print('No script found')
