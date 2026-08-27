def solve_n_queens(n):
       """
       Solve the N-Queens problem using backtracking.
       Returns all valid board configurations where no two queens attack each other.
       """
       solutions = []

       def is_safe(board, row, col):
           # Check left in the same row
           for c in range(col):
               if board[row][c] == 1:
                   return False
           # Check upper-left diagonal
           r, c = row, col
           while r >= 0 and c >= 0:
               if board[r][c] == 1:
                   return False
               r -= 1
               c -= 1
           # Check lower-left diagonal
           r, c = row, col
           while r < n and c >= 0:
               if board[r][c] == 1:
                   return False
               r += 1
               c -= 1
           return True

       def backtrack(board, col):
           if col == n:
               # Save a copy of the current solution
               solution = [
                   "".join("Q" if board[r][c] == 1 else "." for c in range(n))
                   for r in range(n)
               ]
               solutions.append(solution)
               return
           for row in range(n):
               if is_safe(board, row, col):
                   board[row][col] = 1
                   backtrack(board, col + 1)
                   board[row][col] = 0

       initial_board = [[0] * n for _ in range(n)]
       backtrack(initial_board, 0)
       return solutions


   if __name__ == "__main__":
       try:
           n = int(input("Enter the number of queens (n): "))
           if n < 1:
               raise ValueError("n must be a positive integer.")
           sols = solve_n_queens(n)
           print(f"\nTotal solutions for {n}-Queens: {len(sols)}")
           for i, sol in enumerate(sols, 1):
               print(f"\nSolution {i}:")
               for row in sol:
                   print(" ".join(row))
       except ValueError as e:
           print(f"Invalid input: {e}")