"""Proveedor simulado: protocolo diferente al contrato de la aplicacion."""
from http.server import BaseHTTPRequestHandler, HTTPServer
import json

class Handler(BaseHTTPRequestHandler):
    failing = False
    def do_POST(self):
        length = int(self.headers.get('Content-Length', 0))
        data = json.loads(self.rfile.read(length) or b'{}')
        if self.path == '/control':
            Handler.failing = bool(data.get('failing'))
            self.reply(200, {'failing': Handler.failing})
        elif self.path == '/executeTransaction':
            if Handler.failing:
                self.reply(503, {'error': 'Fallo simulado'})
            else:
                self.reply(200, {'reference': 'SIMULADO-' + str(data['code']), 'value': data['value']})
        else:
            self.reply(404, {'error': 'Ruta inexistente'})
    def reply(self, status, body):
        raw = json.dumps(body).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

HTTPServer(('0.0.0.0', 8080), Handler).serve_forever()
