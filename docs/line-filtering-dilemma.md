# Line Filtering Dilemma

## The Problem

EmailDSL needs to extract valid DSL commands from email bodies while filtering out noise like greetings and signatures. The `parse_lines()` method uses line-based filtering to accomplish this, but it has a fundamental tension:

1. **Must keep**: DSL lines (starting with `#:-!@`) and body content
2. **Must skip**: Email noise ("Hi there!", "Sent from my iPhone")
3. **The catch**: Body content doesn't start with special characters

## Current Solution: Brace Depth Tracking

The current implementation tracks brace depth to know when we're inside a body:

```python
def parse_lines(self, text: str) -> Document:
    filtered_lines = []
    brace_depth = 0

    for line in text.split("\n"):
        stripped = line.lstrip()
        open_braces = line.count("{")
        close_braces = line.count("}")

        # Keep line if it starts with special char OR we're inside a body
        if brace_depth > 0 or (stripped and stripped[0] in "#:-!@"):
            filtered_lines.append(line)

        # Update brace depth after processing the line
        brace_depth += open_braces - close_braces
        brace_depth = max(0, brace_depth)

    filtered_text = "\n".join(filtered_lines)
    return self.parse(filtered_text)
```

**Works for:**
- Simple bodies without code
- Bodies with balanced braces
- Filtering email signatures

**Fails for:**
- Code with unbalanced braces in string literals
- Code with unbalanced braces in comments
- Any content where character counting != semantic structure

## Test Cases

### Test 1: Simple Case (✓ Works)
```
Hi there!

#ideas
-task1 { description }

Sent from my iPhone
```

**Result:** Correctly filters noise, keeps DSL

---

### Test 2: Multi-line Body (✓ Works)
```
#ideas
-task1 {
  This is a longer
  description
}
-task2
```

**Result:** Keeps all body content lines

---

### Test 3: Balanced Braces in Code (✓ Works)
```
#code
-snippet {{
  printf("{test}");
}}
```

**Brace tracking:**
- `{{` → depth 2
- `printf("{test}");` → +1-1=0, depth stays 2
- `}}` → depth 0

**Result:** Works because braces balance on each line

---

### Test 4: Unbalanced Braces in String (✗ Fails)
```
#code
-snippet {{
  printf("{test");
}}
This should be noise
-item2
```

**Brace tracking:**
- `{{` → depth 2
- `printf("{test");` → +1, depth becomes 3
- `}}` → -2, depth becomes 1 (WRONG! Should be 0)
- "This should be noise" → KEPT (wrong, depth still 1)
- `-item2` → KEPT (still at depth 1)

**Result:** Parser fails because noise is included in body text

**Error:**
```
Unexpected token Token('BODY_TEXT_SINGLE', 'This should be filtered as noise\n-item2')
```

---

### Test 5: Comment with Unbalanced Brace (✗ Fails)
```
#code
-snippet {{
  // Opening brace here: {
  return 0;
}}
Noise after
```

**Brace tracking:**
- `{{` → depth 2
- `// Opening brace here: {` → +1, depth 3
- `return 0;` → depth 3
- `}}` → -2, depth 1 (WRONG!)
- "Noise after" → KEPT (wrong)

**Result:** Same failure mode

---

### Test 6: Double Braces with Nested (✓ Works... Sometimes)
```
#code
-snippet {{
  code with { nested } braces
}}
```

**Brace tracking:**
- `{{` → depth 2
- `code with { nested } braces` → +1-1=0, depth 2
- `}}` → depth 0

**Result:** Works because inner braces balance

---

## The Fundamental Issue

**Character counting is not semantic parsing.**

The brace counter sees:
- `printf("{` → opening brace
- `// {` → opening brace
- `"}` → closing brace

But semantically:
- Braces in string literals don't affect structure
- Braces in comments don't affect structure
- Only "real" braces in the DSL syntax matter

**The dilemma:** To filter lines correctly, we need to understand semantic structure. But to understand semantic structure, we need to parse. But to parse, we need to filter lines first (to remove noise). Circular dependency!

## Possible Solutions

### Option 1: Accept the Limitation
**Approach:** Document that code bodies with unbalanced braces in strings/comments may cause issues.

**Pros:**
- Simple, no code changes
- Rare edge case in practice
- Users can work around it (balance braces, use double-brace carefully)

**Cons:**
- Can cause confusing parse failures
- Not "correct" behavior

---

### Option 2: Detect Code Blocks
**Approach:** Look for markers like triple backticks or `{{` and skip all line filtering inside them.

```python
in_code_block = False
in_double_brace = False

for line in lines:
    if '```' in line:
        in_code_block = not in_code_block
    if '{{' in line:
        in_double_brace = True
    if '}}' in line:
        in_double_brace = False

    if in_code_block or in_double_brace:
        keep_all_lines()
```

**Pros:**
- Handles most real-world cases
- Still filters email noise outside code blocks

**Cons:**
- More complex heuristics
- Still not perfect (what if code has triple backticks in it?)

---

### Option 3: No Line Filtering
**Approach:** Parse the entire email as-is. Handle parse errors gracefully.

**Pros:**
- No filtering bugs
- Simple to understand

**Cons:**
- "Hi there!" at the start causes parse failure
- Need robust error handling and recovery
- Loses the "ignore email signatures" feature

---

### Option 4: Lark Error Recovery
**Approach:** Use Lark's built-in error recovery to skip invalid tokens and continue parsing.

```python
parser = Lark(grammar, parser='lalr', ambiguity='resolve')
```

**Pros:**
- Most robust solution
- Handles arbitrary malformed input

**Cons:**
- Complex to implement correctly
- May produce unexpected results (silently skipping valid content?)
- Harder to debug

---

### Option 5: Multi-Pass Parsing
**Approach:**
1. Try parsing the whole text
2. On failure, try parse_lines with filtering
3. On failure, try parsing individual lines and collecting what works

**Pros:**
- Graceful degradation
- Handles both clean and noisy inputs

**Cons:**
- Performance cost (multiple parse attempts)
- Still doesn't solve the fundamental issue

---

### Option 6: Stateful Line Filter
**Approach:** Actually tokenize and track state properly:

```python
class StatefulFilter:
    def __init__(self):
        self.in_string = False
        self.in_comment = False
        self.brace_depth = 0

    def process_line(self, line):
        # Track string literals: "..." or '...'
        # Track comments: // or /* */
        # Only count braces outside strings/comments
        ...
```

**Pros:**
- More correct than simple counting
- Still allows line-based filtering

**Cons:**
- Very complex - basically writing a lexer
- Language-specific (Python strings vs C strings vs...)
- Easy to get wrong

---

## Real-World Frequency

How often does this actually happen?

**Requirements for the bug:**
1. Email contains DSL commands ✓ (common)
2. Body contains code ✓ (medium)
3. Code has unbalanced braces in strings/comments ✓ (medium)
4. There's noise text after the body ✓ (medium)
5. That noise doesn't start with special characters ✓ (medium)

**Probability:** Medium × Medium × Medium = Uncommon but not rare

**User impact:** Parse failure with confusing error message

---

## Recommendation

**Short term:** Option 1 (Document limitation) or Option 2 (Detect code blocks)

**Long term:** Consider Option 4 (Lark error recovery) for robustness

**Workaround for users:**
- Use balanced braces in code examples
- Put noise/signatures before DSL commands (top of email)
- Use double braces `{{ }}` for complex code
- Keep emails clean (just DSL, no extra text)

---

## Related Files

- `src/parser.py` - `parse_lines()` implementation
- `tests/test_parser.py` - Test cases
- `tests/data/regex-builders.sorter` - Real-world example that triggered this investigation

---

## Questions to Consider

1. Should line filtering be opt-in rather than default?
2. Should we have separate modes: "strict" (no filtering) vs "lenient" (with filtering)?
3. Can we detect when filtering is likely to fail and fall back to strict mode?
4. Should the webhook use different logic than manual parsing?
5. Is this worth the complexity, or should we just tell users "keep emails clean"?
