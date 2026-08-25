"""
   Reads two integers from standard input, validates them,
   prints their sum, and handles edge cases gracefully.
   """

   import sys


   def solve() -> None:
       data = sys.stdin.read().strip().split()
       if len(data) < 2:
           print("Error: expected two integers as input.", file=sys.stderr)
           sys.exit(1)
       if len(data) > 2:
           print("Warning: extra input ignored; only the first two integers will be used.", file=sys.stderr)
       try:
           a, b = int(data[0]), int(data[1])
       except ValueError:
           print("Error: both inputs must be valid integers.", file=sys.stderr)
           sys.exit(1)
       print(a + b)


   if __name__ == "__main__":
       solve()