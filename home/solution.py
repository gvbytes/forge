"""
Snake Game with Local HTTP Server
Provides a playable Snake game via tkinter and serves a local URL for access.
"""
import tkinter as tk
import random
import threading
import http.server
import socketserver
import webbrowser


class SnakeGame:
    """A simple Snake game implemented with tkinter."""
    def __init__(self, root):
        self.root = root
        self.root.title("Snake Game")
        self.root.resizable(False, False)
        self.canvas = tk.Canvas(root, width=400, height=400, bg="black")
        self.canvas.pack()
        self.score = 0
        self.direction = "Right"
        self.snake = [[200, 200], [190, 200], [180, 200]]
        self.food = self._spawn_food()
        self.game_over = False
        self.root.bind("<Left>", lambda e: self._change_dir("Left"))
        self.root.bind("<Right>", lambda e: self._change_dir("Right"))
        self.root.bind("<Up>", lambda e: self._change_dir("Up"))
        self.root.bind("<Down>", lambda e: self._change_dir("Down"))
        self._update()

    def _spawn_food(self):
        while True:
            x = random.randint(0, 39) * 10
            y = random.randint(0, 39) * 10
            if [x, y] not in self.snake:
                return [x, y]

    def _change_dir(self, d):
        if self.game_over:
            return
        opposites = {"Left": "Right", "Right": "Left", "Up": "Down", "Down": "Up"}
        if self.direction != opposites.get(d):
            self.direction = d

    def _update(self):
        if self.game_over:
            return
        x, y = self.snake[0]
        if self.direction == "Left":
            x -= 10
        elif self.direction == "Right":
            x += 10
        elif self.direction == "Up":
            y -= 10
        elif self.direction == "Down":
            y += 10

        new_head = [x, y]
        # Wall or self collision
        if x < 0 or x >= 400 or y < 0 or y >= 400 or new_head in self.snake:
            self.game_over = True
            self.canvas.create_text(200, 200, text=f"Game Over! Score: {self.score}", fill="white", font=("Arial", 16))
            return

        self.snake.insert(0, new_head)
        if new_head == self.food:
            self.score += 10
            self.food = self._spawn_food()
        else:
            self.snake.pop()

        self.canvas.delete("all")
        self.canvas.create_oval(self.food[0], self.food[1], self.food[0]+10, self.food[1]+10, fill="red")
        for seg in self.snake:
            self.canvas.create_rectangle(seg[0], seg[1], seg[0]+10, seg[1]+10, fill="lime")
        self.root.after(100, self._update)


def run_local_server(port=8000):
    handler = http.server.SimpleHTTPRequestHandler
    with socketserver.TCPServer(("", port), handler) as httpd:
        url = f"http://localhost:{port}"
        print(f"\n🔗 Local URL: {url}")
        webbrowser.open(url)
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()


if __name__ == "__main__":
    root = tk.Tk()
    game = SnakeGame(root)
    server_thread = threading.Thread(target=run_local_server, args=(8000,), daemon=True)
    server_thread.start()
    root.mainloop()