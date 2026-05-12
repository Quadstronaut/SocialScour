# Build Prompt: PunyPython-Style Roman Numeral Converter

Build a tiny Python program in the current directory. Keep it small and direct — PunyPython style: one obvious thing, no abstractions.

## Goals
1. Provide bidirectional Roman numeral conversion in `roman.py`.
2. Provide a self-contained smoke test in `test_roman.py` that uses plain `assert` (no pytest, no unittest framework needed — just `python test_roman.py`).

## Stack
- Python 3.11+ standard library only. No external packages.

## File layout
```
aider-test/
  roman.py
  test_roman.py
```

## `roman.py` contract
Define exactly these two functions and nothing else of substance at module level (you may include a `__main__` block that prints `to_roman(1994)` if you like, but it's optional):

- `to_roman(n: int) -> str` — convert an integer in the range 1..3999 inclusive to its Roman numeral string. Raise `ValueError` for anything outside that range.
- `from_roman(s: str) -> int` — parse a Roman numeral string back to the integer. Raise `ValueError` if the string is not a well-formed canonical Roman numeral in 1..3999. To enforce canonical form, after computing the integer round-trip it through `to_roman` and raise `ValueError` if `to_roman(result) != s` — that rejects non-canonical forms like `"IIII"` or `"VV"`.

Use the standard subtractive notation: `IV` (4), `IX` (9), `XL` (40), `XC` (90), `CD` (400), `CM` (900). So `1994` → `"MCMXCIV"` and `from_roman("MCMXCIV")` → `1994`.

## `test_roman.py` contract
Imports `to_roman` and `from_roman` from `roman` and runs assertions covering:
- `to_roman(1) == "I"`
- `to_roman(4) == "IV"`
- `to_roman(9) == "IX"`
- `to_roman(40) == "XL"`
- `to_roman(1994) == "MCMXCIV"`
- `to_roman(3999) == "MMMCMXCIX"`
- `from_roman("I") == 1`
- `from_roman("MCMXCIV") == 1994`
- Round-trip: for n in [1, 4, 9, 40, 49, 99, 400, 944, 1994, 2024, 3999], `from_roman(to_roman(n)) == n`
- Out-of-range raises: `to_roman(0)` and `to_roman(4000)` must each raise `ValueError`.
- Malformed input raises: `from_roman("IIII")` and `from_roman("ABC")` must each raise `ValueError`.

End the file with `print("OK")` after the last assertion so a successful run prints `OK`.

## Acceptance check
```
python aider-test/test_roman.py
```
Exit code 0 and the last line of stdout is `OK`.

That's it. Two files. Don't add a README, a pyproject.toml, or anything else.
