"""
Sample app for demonstrating qa_mcp end to end.

A tiny checkout API + storefront page, built on Python's stdlib only (no
Flask/FastAPI needed) so this demo has zero extra dependencies beyond what
qa_mcp already requires. It has two INTENTIONAL bugs, left in on purpose so
the qa_mcp demo report (see run_demo.py) has real failures with real root
causes to show, not just a wall of green checkmarks:

  BUG 1 (business logic): POST /api/checkout does not check that
  coupon_code discount <= amount, so a large enough coupon produces a
  negative order total.

  BUG 2 (API): GET /api/orders/<id> for an order that doesn't exist
  returns 200 with an empty body instead of 404.
"""
import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

ORDERS = {
    "1": {"id": "1", "email": "alice@example.com", "amount": 100, "coupon_code": None, "total": 100},
}

STATIC_DIR = Path(__file__).parent


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _json(self, status, body):
        payload = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self):
        if self.path == "/" or self.path == "/checkout.html":
            content = (STATIC_DIR / "checkout.html").read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
            return

        if self.path.startswith("/api/orders/"):
            order_id = self.path.rsplit("/", 1)[-1]
            order = ORDERS.get(order_id)
            if order:
                self._json(200, order)
            else:
                # BUG 2: should be 404, returns 200 with an empty body instead.
                self._json(200, {})
            return

        self._json(404, {"error": "not found"})

    def do_POST(self):
        if self.path != "/api/checkout":
            self._json(404, {"error": "not found"})
            return

        length = int(self.headers.get("Content-Length", 0))
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            self._json(400, {"error": "malformed JSON body"})
            return

        email = body.get("email")
        amount = body.get("amount")
        coupon_code = body.get("coupon_code")

        if not email:
            self._json(400, {"error": "email is required"})
            return
        if amount is None or not isinstance(amount, (int, float)):
            self._json(400, {"error": "amount is required and must be a number"})
            return

        discount = 20 if coupon_code == "SAVE20" else (1000 if coupon_code == "HUGE1000" else 0)
        total = amount - discount  # BUG 1: no floor at 0 - a large enough coupon goes negative

        order_id = str(len(ORDERS) + 1)
        order = {"id": order_id, "email": email, "amount": amount, "coupon_code": coupon_code, "total": total}
        ORDERS[order_id] = order
        self._json(201, order)


def run(port=0):
    server = HTTPServer(("127.0.0.1", port), Handler)
    return server


if __name__ == "__main__":
    server = run(8420)
    print(f"checkout-demo running at http://127.0.0.1:8420")
    server.serve_forever()
