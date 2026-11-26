"""Allow the sandboxed plugin iframe only on its two token-scoped endpoints."""
from starlette.middleware.cors import CORSMiddleware


class FigmaPluginCORSMiddleware:
    def __init__(self, app):
        self.app = app
        self.plugin = CORSMiddleware(app, allow_origins=['null', 'https://www.figma.com'],
                                    allow_methods=['POST'], allow_headers=['Authorization', 'Content-Type'])

    async def __call__(self, scope, receive, send):
        plugin_path = scope.get('path') in ('/api/figma-plugin/pair', '/api/figma-plugin/snapshot',
                                          '/api/figma-plugin/resume', '/api/figma-plugin/changes')
        target = self.plugin if scope['type'] == 'http' and plugin_path else self.app
        await target(scope, receive, send)
