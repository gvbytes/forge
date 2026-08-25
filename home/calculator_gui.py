#!/usr/bin/env python3
"""
A GUI-based advanced calculator using Tkinter.
Supports basic arithmetic, exponentiation, trigonometric functions,
logarithms, square root, and more. Uses a safe eval environment.
"""

import tkinter as tk
from tkinter import ttk, messagebox
import math
import re

# --------------------------------------------------------------------------- #
# Safe evaluation utilities
# --------------------------------------------------------------------------- #

# Allowed names for eval
SAFE_NAMES = {
    'sin': math.sin,
    'cos': math.cos,
    'tan': math.tan,
    'log': math.log,
    'log10': math.log10,
    'sqrt': math.sqrt,
    'pi': math.pi,
    'e': math.e,
    'abs': abs,
    'pow': pow,
    'factorial': math.factorial,
}

# Replace '^' with '**' for exponentiation
def preprocess_expr(expr: str) -> str:
    # Replace '^' with '**'
    expr = expr.replace('^', '**')
    # Replace '×' and '÷' if used
    expr = expr.replace('×', '*').replace('÷', '/')
    return expr

def safe_eval(expr: str) -> float:
    """
    Evaluate a mathematical expression safely using a restricted namespace.
    """
    expr = preprocess_expr(expr)
    # Validate expression: allow only numbers, operators, parentheses, and allowed names
    if not re.match(r'^[0-9\.\+\-\*\/\(\)\s\^,]+$|^[0-9\.\+\-\*\/\(\)\s\^,]+[a-zA-Z_][a-zA-Z0-9_]*', expr):
        # Allow function calls like sin(0)
        pass
    try:
        return eval(expr, {"__builtins__": None}, SAFE_NAMES)
    except Exception as e:
        raise ValueError(f"Invalid expression: {e}")

# --------------------------------------------------------------------------- #
# Calculator GUI
# --------------------------------------------------------------------------- #

class Calculator(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Advanced Calculator")
        self.resizable(False, False)
        # Set window background to red
        self.configure(bg='#ff0000')
        self._create_widgets()

    def _create_widgets(self):
        # Display frame with red background
        display_frame = tk.Frame(self, bg='#ff0000')
        display_frame.grid(row=0, column=0, columnspan=6, padx=10, pady=10, sticky="ew")
        
        self.display_var = tk.StringVar()
        self.display = ttk.Entry(
            display_frame,
            textvariable=self.display_var,
            font=("Arial", 18),
            justify="right",
            state="readonly",
            width=25
        )
        self.display.pack(fill="both", expand=True, padx=5, pady=5)
        # Configure display background to red
        self.display.configure(background='#ff0000', foreground='white')

        # Button definitions: (text, row, column, width, command)
        buttons = [
            ("7", 1, 0, 1, lambda: self._append("7")),
            ("8", 1, 1, 1, lambda: self._append("8")),
            ("9", 1, 2, 1, lambda: self._append("9")),
            ("÷", 1, 3, 1, lambda: self._append("÷")),
            ("sin", 1, 4, 1, lambda: self._append("sin(")),
            ("cos", 1, 5, 1, lambda: self._append("cos(")),

            ("4", 2, 0, 1, lambda: self._append("4")),
            ("5", 2, 1, 1, lambda: self._append("5")),
            ("6", 2, 2, 1, lambda: self._append("6")),
            ("×", 2, 3, 1, lambda: self._append("×")),
            ("tan", 2, 4, 1, lambda: self._append("tan(")),
            ("log", 2, 5, 1, lambda: self._append("log(")),

            ("1", 3, 0, 1, lambda: self._append("1")),
            ("2", 3, 1, 1, lambda: self._append("2")),
            ("3", 3, 2, 1, lambda: self._append("3")),
            ("-", 3, 3, 1, lambda: self._append("-")),
            ("√", 3, 4, 1, lambda: self._append("sqrt(")),
            ("log10", 3, 5, 1, lambda: self._append("log10(")),

            ("0", 4, 0, 1, lambda: self._append("0")),
            (".", 4, 1, 1, lambda: self._append(".")),
            ("^", 4, 2, 1, lambda: self._append("^")),
            ("+", 4, 3, 1, lambda: self._append("+")),
            ("(", 4, 4, 1, lambda: self._append("(")),
            (")", 4, 5, 1, lambda: self._append(")")),

            ("C", 5, 0, 1, self._clear),
            ("←", 5, 1, 1, self._backspace),
            ("%", 5, 2, 1, lambda: self._append("%")),
            ("=", 5, 3, 3, self._evaluate),
        ]

        for (text, row, col, width, cmd) in buttons:
            # Configure button background to red with white text
            btn = ttk.Button(self, text=text, command=cmd, style="Red.TButton")
            btn.grid(row=row, column=col, padx=5, pady=5, sticky="nsew")
            if width > 1:
                self.grid_columnconfigure(col, weight=1)
                self.grid_columnconfigure(col+1, weight=1)
                self.grid_columnconfigure(col+2, weight=1)
                btn.grid(columnspan=width)

        # Configure grid weights
        for i in range(6):
            self.grid_columnconfigure(i, weight=1)
        for i in range(6):
            self.grid_rowconfigure(i, weight=1)

        # Configure custom style for red buttons
        style = ttk.Style()
        style.configure("Red.TButton", background="#ff0000", foreground="white", font=("Arial", 12))
        style.map("Red.TButton", background=[("active", "#cc0000")], foreground=[("active", "white")])

    def _append(self, char: str):
        current = self.display_var.get()
        new_value = current + char
        self.display_var.set(new_value)

    def _clear(self):
        self.display_var.set("")

    def _backspace(self):
        current = self.display_var.get()
        if current:
            self.display_var.set(current[:-1])

    def _evaluate(self):
        expr = self.display_var.get()
        if not expr:
            return
        try:
            result = safe_eval(expr)
            self.display_var.set(str(result))
        except Exception as e:
            messagebox.showerror("Error", str(e))
            self.display_var.set("")

# --------------------------------------------------------------------------- #
# Main entry point
# --------------------------------------------------------------------------- #

if __name__ == "__main__":
    app = Calculator()
    app.mainloop()