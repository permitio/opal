from tests.containers.permitContainer import PermitContainer


class BroadcastContainerBase(PermitContainer):
    def __init__(self):
        PermitContainer.__init__(self)

    def get_url(self) -> str:
        url = (
            self.settings.protocol
            + "://"
            + self.settings.user
            + ":"
            + self.settings.password
            + "@"
            + self.settings.container_name
            + ":"
            + str(self.settings.port)
        )
        print(url)
        return url
