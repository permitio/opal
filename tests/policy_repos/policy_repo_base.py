from abc import ABC, abstractmethod


class PolicyRepoBase(ABC):
    @abstractmethod
    def get_repo_url(self) -> str:
        pass

    @abstractmethod
    def setup_webhooks(self, host, port):
        pass
    @abstractmethod
    def setup(self) -> None:
        pass

    @abstractmethod
    def cleanup(self) -> None:
        pass

    @abstractmethod
    def update_branch(self, file_name, file_content) -> None:
        pass

    @abstractmethod
    def create_webhook(self):
        pass
