
if __name__ == '__main__':
    from .opal_server import OpalServer
    server = OpalServer()
    app = server.app
