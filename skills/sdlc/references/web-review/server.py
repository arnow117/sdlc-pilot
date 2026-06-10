#!/usr/bin/env python3
"""spec-web-review 回收服务器(零依赖)。
GET  /            → index.html(批注页)
POST /feedback    → 把 body 写到 feedback.json,供 agent 读取
用法: python3 server.py [port]
"""
import http.server, socketserver, os, sys

DIR = os.path.dirname(os.path.abspath(__file__))
PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8777


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **k):
        super().__init__(*a, directory=DIR, **k)

    def do_POST(self):
        if self.path.rstrip('/') == '/feedback':
            n = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(n)
            with open(os.path.join(DIR, 'feedback.json'), 'wb') as f:
                f.write(body)
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(b'{"ok":true}')
            print('[feedback] received %d bytes -> feedback.json' % len(body))
        else:
            self.send_response(404)
            self.end_headers()

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'POST,OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def log_message(self, *a):
        pass  # 静默普通请求日志


socketserver.TCPServer.allow_reuse_address = True
with socketserver.TCPServer(('127.0.0.1', PORT), Handler) as httpd:
    print('spec-web-review serving on http://127.0.0.1:%d  (Ctrl+C 停止)' % PORT)
    httpd.serve_forever()
