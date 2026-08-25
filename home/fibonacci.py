def fibonacci(n):
    """Return the nth Fibonacci number (0-indexed)."""
    if not isinstance(n, int) or n < 0:
        raise ValueError("Input must be a non-negative integer.")
    if n == 0:
        return 0
    if n == 1:
        return 1
    a, b = 0, 1
    for _ in range(2, n + 1):
        a, b = b, a + b
    return b

if __name__ == "__main__":
    try:
        n = int(input("Enter a non-negative integer: "))
        print(f"Fibonacci({n}) = {fibonacci(n)}")
    except ValueError as e:
        print(e)