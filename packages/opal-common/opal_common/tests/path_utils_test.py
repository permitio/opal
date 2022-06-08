import os
import sys

import pytest

# Add root opal dir to use local src as package for tests (i.e, no need for python -m pytest)
root_dir = os.path.abspath(
    os.path.join(
        os.path.dirname(__file__),
        os.path.pardir,
        os.path.pardir,
    )
)
sys.path.append(root_dir)

from pathlib import Path
from typing import List

from opal_common.paths import PathUtils


def to_paths(paths: List[str]) -> List[Path]:
    return [Path(path) for path in paths]


def test_intermediate_directories():
    # empty sources returns empty parent list
    assert len(PathUtils.intermediate_directories(to_paths([]))) == 0
    # '/', '.' and '' has no parent
    assert len(PathUtils.intermediate_directories(to_paths(["/"]))) == 0
    assert len(PathUtils.intermediate_directories(to_paths(["."]))) == 0
    assert len(PathUtils.intermediate_directories(to_paths([""]))) == 0
    # top level directories has only one parent
    assert PathUtils.intermediate_directories(to_paths(["/some"])) == to_paths(["/"])
    assert PathUtils.intermediate_directories(to_paths(["some"])) == to_paths(["."])
    # check some examples of nested paths
    parents = PathUtils.intermediate_directories(to_paths(["some/dir/to"]))
    assert len(parents) == 3
    assert len(set(parents).intersection(set(to_paths([".", "some", "some/dir"])))) == 3
    parents = PathUtils.intermediate_directories(to_paths(["/another/example"]))
    assert len(parents) == 2
    assert len(set(parents).intersection(set(to_paths(["/", "/another"])))) == 2
    # mix and match
    parents = PathUtils.intermediate_directories(
        to_paths(
            [
                "some",
                "/other",
                "example/of/path",
                "some/may/intersect",
            ]
        )
    )
    assert len(parents) == 6
    assert Path(".") in parents
    assert Path("/") in parents
    assert Path("some") in parents
    assert Path("some/may") in parents
    assert Path("example") in parents
    assert Path("example/of") in parents


def test_is_child_of_directories():
    # parent directories are the top level (relative) dir
    assert PathUtils.is_child_of_directories(Path("."), set(to_paths(["."]))) == False
    assert (
        PathUtils.is_child_of_directories(Path("hello"), set(to_paths(["."]))) == True
    )
    assert (
        PathUtils.is_child_of_directories(Path("world.txt"), set(to_paths(["."])))
        == True
    )
    assert (
        PathUtils.is_child_of_directories(Path("/world"), set(to_paths(["."]))) == False
    )

    # parent directories are the top level (absolute) dir
    assert PathUtils.is_child_of_directories(Path("/"), set(to_paths(["/"]))) == False
    assert (
        PathUtils.is_child_of_directories(Path("/hello"), set(to_paths(["/"]))) == True
    )
    assert (
        PathUtils.is_child_of_directories(Path("/world.txt"), set(to_paths(["/"])))
        == True
    )
    assert (
        PathUtils.is_child_of_directories(Path("world"), set(to_paths(["/"]))) == False
    )

    # directories can be files (bad input)
    assert (
        PathUtils.is_child_of_directories(
            Path("/world.txt"), set(to_paths(["/hello.txt"]))
        )
        == False
    )

    # some valid input
    assert (
        PathUtils.is_child_of_directories(
            Path("some/file.txt"), set(to_paths(["some"]))
        )
        == True
    )
    assert (
        PathUtils.is_child_of_directories(Path("some/file.txt"), set(to_paths(["."])))
        == True
    )
    assert (
        PathUtils.is_child_of_directories(
            Path("some/dir/to/file.txt"), set(to_paths(["some/dir"]))
        )
        == True
    )


def test_filter_children_paths_of_directories():
    sources = to_paths(
        [
            "/files/for/testing/1.txt",
            "/files/for/testing/2.json",
            "/filtered/out.txt",
            "relative/path.log",
            "relative/subdir/another.log",
        ]
    )
    # filter paths under .
    paths = PathUtils.filter_children_paths_of_directories(
        sources, set(to_paths(["."]))
    )
    assert len(paths) == 2
    assert (
        len(
            set(paths).intersection(
                set(to_paths(["relative/path.log", "relative/subdir/another.log"]))
            )
        )
        == 2
    )

    # filter paths under /
    paths = PathUtils.filter_children_paths_of_directories(
        sources, set(to_paths(["/"]))
    )
    assert len(paths) == 3
    assert (
        len(
            set(paths).intersection(
                set(
                    to_paths(
                        [
                            "/files/for/testing/1.txt",
                            "/files/for/testing/2.json",
                            "/filtered/out.txt",
                        ]
                    )
                )
            )
        )
        == 3
    )

    # filter paths under /files
    paths = PathUtils.filter_children_paths_of_directories(
        sources, set(to_paths(["/files"]))
    )
    assert len(paths) == 2
    assert (
        len(
            set(paths).intersection(
                set(
                    to_paths(
                        [
                            "/files/for/testing/1.txt",
                            "/files/for/testing/2.json",
                        ]
                    )
                )
            )
        )
        == 2
    )

    # filter paths under relative/subdir
    paths = PathUtils.filter_children_paths_of_directories(
        sources, set(to_paths(["relative/subdir"]))
    )
    assert len(paths) == 1
    assert (
        len(
            set(paths).intersection(
                set(
                    to_paths(
                        [
                            "relative/subdir/another.log",
                        ]
                    )
                )
            )
        )
        == 1
    )

    # filter paths under multiple parents
    paths = PathUtils.filter_children_paths_of_directories(
        sources, set(to_paths(["relative/subdir", "/filtered"]))
    )
    assert len(paths) == 2
    assert (
        len(
            set(paths).intersection(
                set(
                    to_paths(
                        [
                            "/filtered/out.txt",
                            "relative/subdir/another.log",
                        ]
                    )
                )
            )
        )
        == 2
    )

    # parents can intersect
    paths = PathUtils.filter_children_paths_of_directories(
        sources, set(to_paths(["relative/subdir", "."]))
    )
    assert len(paths) == 2
    assert (
        len(
            set(paths).intersection(
                set(to_paths(["relative/path.log", "relative/subdir/another.log"]))
            )
        )
        == 2
    )

    # no parents
    paths = PathUtils.filter_children_paths_of_directories(sources, set())
    assert len(paths) == 0

    # no parent match sources
    paths = PathUtils.filter_children_paths_of_directories(
        sources, set(to_paths(["not/in/repo"]))
    )
    assert len(paths) == 0


def test_non_intersecting_directories():
    # assert PathUtils.is_child_of_directories(Path('/hello'), set(to_paths(['/']))) == True

    # relative paths are all displaced by '.'
    assert PathUtils.non_intersecting_directories(
        to_paths([".", "hello", "world"])
    ) == set(to_paths(["."]))

    # absolute paths are all displaced by '/'
    assert PathUtils.non_intersecting_directories(
        to_paths(["/", "/hello", "/hello/world"])
    ) == set(to_paths(["/"]))

    # parents displace children
    assert PathUtils.non_intersecting_directories(
        to_paths(["/hello", "/hello/world", "world", "world/of/tomorrow"])
    ) == set(to_paths(["/hello", "world"]))


def test_sort_paths_according_to_explicit_sorting():
    sort_func = PathUtils.sort_paths_according_to_explicit_sorting

    # empty list cannot be sorted
    assert sort_func([], []) == []
    assert sort_func([], to_paths([".", "hello", "world"])) == []

    # if no sorting is available, returns the original list
    examples = [
        to_paths([".", "hello", "world"]),
        to_paths(["world.rego", "lib.rego", "./unrelated.rego"]),
        to_paths(["/", "./unrelated.rego"]),
    ]
    for example in examples:
        assert sort_func(example, []) == example

    # partial sorting works as expected
    assert sort_func(
        to_paths([".", "world.rego", "lib.rego", "more/path.rego", "even/more"]),
        # ordering
        to_paths(["lib.rego", "world.rego"]),
        # explicitly sorted items move to the beginning of the list
        # other items remain in the original sorting
    ) == to_paths(["lib.rego", "world.rego", ".", "more/path.rego", "even/more"])

    # same list, switch the ordering
    assert sort_func(
        to_paths([".", "world.rego", "lib.rego", "more/path.rego", "even/more"]),
        # ordering
        to_paths(["world.rego", "lib.rego"]),
        # explicitly sorted items move to the beginning of the list
        # other items remain in the original sorting
    ) == to_paths(["world.rego", "lib.rego", ".", "more/path.rego", "even/more"])

    # some sorting items are not found
    assert sort_func(
        to_paths([".", "world.rego", "lib.rego", "more/path.rego", "even/more"]),
        # ordering
        to_paths(["world.rego", "lib2.rego"]),
        # explicitly sorted items move to the beginning of the list
        # other items remain in the original sorting
    ) == to_paths(["world.rego", ".", "lib.rego", "more/path.rego", "even/more"])
