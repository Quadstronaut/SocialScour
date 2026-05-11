def to_roman(n):
    if not 1 <= n <= 3999:
        raise ValueError("Input must be between 1 and 3999")
    
    values = [1000, 900, 500, 400, 100, 90, 50, 40, 10, 9, 5, 4, 1]
    numerals = ["M", "CM", "D", "CD", "C", "XC", "L", "XL", "X", "IX", "V", "IV", "I"]
    
    result = ""
    for i in range(len(values)):
        count = n // values[i]
        result += numerals[i] * count
        n -= values[i] * count
    return result


def from_roman(s):
    roman_values = {
        'I': 1, 'V': 5, 'X': 10, 'L': 50,
        'C': 100, 'D': 500, 'M': 1000
    }
    
    total = 0
    prev_value = 0
    
    for char in reversed(s):
        if char not in roman_values:
            raise ValueError("Invalid Roman numeral character")
        value = roman_values[char]
        if value < prev_value:
            total -= value
        else:
            total += value
        prev_value = value
    
    # Check if the result is valid and canonical
    if not 1 <= total <= 3999:
        raise ValueError("Roman numeral out of range")
    
    if to_roman(total) != s:
        raise ValueError("Not a canonical Roman numeral")
    
    return total
