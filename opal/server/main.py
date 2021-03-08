def create_app(*args, **kwargs):
    from .opal_server import OpalServer
    server = OpalServer(*args, **kwargs)
    return server.app

if __name__ == '__main__':
    create_app()
