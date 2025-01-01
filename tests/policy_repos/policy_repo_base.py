from abc import ABC, abstractmethod


class PolicyRepoBase(ABC):
    @abstractmethod
    def get_repo_url(self) -> str:
        pass

    @abstractmethod
    def update_branch(self, file_name, file_content) -> None:
        pass
