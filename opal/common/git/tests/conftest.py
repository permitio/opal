from pathlib import Path
from typing import Union

import pytest
from git import Actor, Repo


class Helpers:
    @staticmethod
    def create_new_file_commit(
        repo: Repo,
        filename: Union[str, Path],
        contents: str = "bla bla\n",
        commit_msg: str = "add file"
    ):
        filename = str(filename)
        open(filename, 'w').write(contents)
        author = Actor("John doe", "john@doe.com")
        repo.index.add([filename])
        repo.index.commit(commit_msg, author=author)

    @staticmethod
    def create_modify_file_commit(
        repo: Repo,
        filename: Union[str, Path],
        contents: str = "more\ncontent\n",
        commit_msg: str = "change file"
    ):
        filename = str(filename)
        open(filename, 'w+').write(contents)
        author = Actor("John doe", "john@doe.com")
        repo.index.add([filename])
        repo.index.commit(commit_msg, author=author)

    @staticmethod
    def create_delete_file_commit(
        repo: Repo,
        filename: Union[str, Path],
        commit_msg: str = "delete file"
    ):
        filename = str(filename)
        author = Actor("John doe", "john@doe.com")
        repo.index.remove([filename], working_tree=True)
        repo.index.commit(commit_msg, author=author)

@pytest.fixture
def helpers() -> Helpers:
    return Helpers()

@pytest.fixture
def local_repo(tmp_path, helpers: Helpers) -> Repo:
    root = tmp_path / "myrepo"
    root.mkdir()
    repo = Repo.init(root)
    helpers.create_new_file_commit(repo, root / "mylist.txt")
    helpers.create_new_file_commit(repo, root / "mylist2.txt")
    helpers.create_new_file_commit(repo, root / "mylist3.txt")
    helpers.create_modify_file_commit(repo, root / "mylist2.txt")
    helpers.create_delete_file_commit(repo, root / "mylist3.txt")
    return repo

@pytest.fixture
def local_repo_clone(local_repo: Repo) -> Repo:
    clone_root = Path(local_repo.working_tree_dir).parent / "myclone"
    return local_repo.clone(clone_root)
