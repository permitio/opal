import pytest
import os
import sys

# Add root opal dir to use local src as package for tests (i.e, no need for python -m pytest)
root_dir = os.path.abspath(
    os.path.join(
        os.path.dirname(__file__),
        os.path.pardir,
        os.path.pardir,
        os.path.pardir,
        os.path.pardir,
    )
)
sys.path.append(root_dir)

from opal.common.opa.parsing import get_rego_package

def test_can_extract_the_correct_package_name():
    """
    The different variations of package names
    (with real examples from opa playground)
    """
    # package in first line, no dots
    assert get_rego_package("""
package play

# Welcome to the Rego playground! Rego (pronounced "ray-go") is OPA's policy language.
#
# Try it out:
# ...

default hello = false

hello {
    m := input.message
    m == "world"
}
"""
    ) == "play"

    # package after comments, two part name
    assert get_rego_package(
"""
# Role-based Access Control (RBAC)
# --------------------------------

package app.rbac

# By default, deny requests.
default allow = false

# Allow admins to do anything.
allow {
	user_is_admin
}

# Allow the action if the user is granted permission to perform the action.
allow {
	# Find grants for the user.
	some grant
	user_is_granted[grant]

	# Check if the grant permits the action.
	input.action == grant.action
	input.type == grant.type
}
"""
    ) == "app.rbac"

    # package after comments, three part name
    assert get_rego_package(
"""
# JWT Decoding
# ------------

package envoy.http.jwt

default allow = false

allow {
	is_post
	is_dogs
	claims.username == "alice"
}

...
"""
    ) == "envoy.http.jwt"

def test_no_package_name_in_file():
    """
    test no package name in module or invalid package
    """
    # no package line
    assert get_rego_package(
"""
default allow = false

allow {
	# The `some` keyword declares local variables. This example declares a local
	# variable called `user_name` (used below).
	some user_name

	input.attributes.request.http.method == "GET"
}
"""
    ) is None

    # package line with invalid contents
    assert get_rego_package(
"""
package envoy.http.urlextract=

default allow = false

allow {
	# The `some` keyword declares local variables. This example declares a local
	# variable called `user_name` (used below).
	some user_name

	input.attributes.request.http.method == "GET"
}
"""
    ) is None

    # empty file
    assert get_rego_package("") is None