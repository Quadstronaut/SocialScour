from roman import to_roman, from_roman

# Test to_roman function
assert to_roman(1) == "I"
assert to_roman(4) == "IV"
assert to_roman(9) == "IX"
assert to_roman(40) == "XL"
assert to_roman(1994) == "MCMXCIV"
assert to_roman(3999) == "MMMCMXCIX"

# Test from_roman function
assert from_roman("I") == 1
assert from_roman("MCMXCIV") == 1994

# Test round-trip
for n in [1, 4, 9, 40, 49, 99, 400, 944, 1994, 2024, 3999]:
    assert from_roman(to_roman(n)) == n

# Test out-of-range raises
try:
    to_roman(0)
    assert False, "Should have raised ValueError"
except ValueError:
    pass

try:
    to_roman(4000)
    assert False, "Should have raised ValueError"
except ValueError:
    pass

# Test malformed input raises
try:
    from_roman("IIII")
    assert False, "Should have raised ValueError"
except ValueError:
    pass

try:
    from_roman("ABC")
    assert False, "Should have raised ValueError"
except ValueError:
    pass

print("OK")
