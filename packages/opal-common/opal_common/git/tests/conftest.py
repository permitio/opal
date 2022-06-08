import json
from pathlib import Path
from typing import Tuple, Union

import pytest
from git import Actor, Repo
from git.objects import Commit

REGO_CONTENTS = """
# Role-based Access Control (RBAC)
# --------------------------------
package {package_name}

# By default, deny requests.
default allow = false
"""


class Helpers:
    @staticmethod
    def rego_contents(package_name: str = "app.rbac") -> str:
        return REGO_CONTENTS.format(package_name=package_name)

    @staticmethod
    def json_contents() -> str:
        return json.dumps({"roles": ["admin"]})

    @staticmethod
    def create_new_file_commit(
        repo: Repo,
        filename: Union[str, Path],
        contents: str = "bla bla\n",
        commit_msg: str = "add file",
    ):
        filename = str(filename)
        open(filename, "w").write(contents)
        author = Actor("John doe", "john@doe.com")
        repo.index.add([filename])
        repo.index.commit(commit_msg, author=author)

    @staticmethod
    def create_modify_file_commit(
        repo: Repo,
        filename: Union[str, Path],
        contents: str = "more\ncontent\n",
        commit_msg: str = "change file",
    ):
        filename = str(filename)
        open(filename, "a").write(contents)
        author = Actor("John doe", "john@doe.com")
        repo.index.add([filename])
        repo.index.commit(commit_msg, author=author)

    @staticmethod
    def create_delete_file_commit(
        repo: Repo, filename: Union[str, Path], commit_msg: str = "delete file"
    ):
        filename = str(filename)
        author = Actor("John doe", "john@doe.com")
        repo.index.remove([filename], working_tree=True)
        repo.index.commit(commit_msg, author=author)

    @staticmethod
    def create_rename_file_commit(
        repo: Repo,
        filename: Union[str, Path],
        new_filename: Union[str, Path],
        commit_msg: str = "rename file",
    ):
        filename = str(filename)
        new_filename = str(new_filename)
        author = Actor("John doe", "john@doe.com")
        repo.index.move([filename, new_filename])
        repo.index.commit(commit_msg, author=author)


@pytest.fixture
def helpers() -> Helpers:
    return Helpers()


@pytest.fixture
def local_repo(tmp_path, helpers: Helpers) -> Repo:
    """creates a dummy repo with the following file structure:

    # .
    # ├── other
    # │   ├── abac.rego
    # │   └── data.json
    # │   └── some.json
    # ├── rbac.rego
    # ├── ignored.json
    # ├── mylist.txt
    # └── some
    #     └── dir
    #         └── to
    #             └── file.rego
    """
    root: Path = tmp_path / "myrepo"
    root.mkdir()
    repo = Repo.init(root)

    # create file to delete later
    helpers.create_new_file_commit(repo, root / "deleted.rego")

    # creating a text file we can modify later
    helpers.create_new_file_commit(repo, root / "mylist.txt")

    # create rego module file at root dir
    helpers.create_new_file_commit(
        repo, root / "rbac.rego", contents=helpers.rego_contents()
    )
    helpers.create_new_file_commit(
        repo, root / "ignored.json", contents=helpers.json_contents()
    )

    # create another rego and data module files at subdirectory
    other = root / "other"
    other.mkdir()
    helpers.create_new_file_commit(
        repo, other / "abac.rego", contents=helpers.rego_contents("app.abac")
    )
    helpers.create_new_file_commit(
        repo, other / "data.json", contents=helpers.json_contents()
    )
    # this json is not an opa data module
    helpers.create_new_file_commit(
        repo, other / "some.json", contents=helpers.json_contents()
    )

    # create another rego at another subdirectory
    somedir = root / "some/dir/to"
    somedir.mkdir(parents=True)
    helpers.create_new_file_commit(
        repo, somedir / "file.rego", contents=helpers.rego_contents("envoy.http.public")
    )

    # create a "modify" commit
    helpers.create_modify_file_commit(repo, root / "mylist.txt")

    # create a "delete" commit
    helpers.create_delete_file_commit(repo, root / "deleted.rego")
    return repo


@pytest.fixture
def local_repo_clone(local_repo: Repo) -> Repo:
    clone_root = Path(local_repo.working_tree_dir).parent / "myclone"
    return local_repo.clone(clone_root)


@pytest.fixture
def repo_with_diffs(local_repo: Repo, helpers: Helpers) -> Tuple[Repo, Commit, Commit]:
    repo: Repo = local_repo
    root = Path(repo.working_tree_dir)

    # save initial state as old commit
    previous_head: Commit = repo.head.commit

    # create "added", "modify", "delete" and "rename" changes
    helpers.create_new_file_commit(
        repo, root / "other/gbac.rego", contents=helpers.rego_contents("app.gbac")
    )
    helpers.create_modify_file_commit(repo, root / "mylist.txt")
    helpers.create_delete_file_commit(repo, root / "other/data.json")
    helpers.create_rename_file_commit(
        repo, root / "ignored.json", root / "ignored2.json"
    )

    # save the new head as the new commit
    new_head: Commit = repo.head.commit

    return (repo, previous_head, new_head)
