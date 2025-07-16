from tests.containers.opal_test_container import OpalTestContainer


class BroadcastContainerBase(OpalTestContainer):
    def __init__(self, **kwargs):
        OpalTestContainer.__init__(self, **kwargs)

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
