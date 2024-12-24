# Hello World
# -----------
#
# This example grants public HTTP access to "/", full access to "charlie", and
# blocks everything else. This example shows how to:
#
#	* Construct a simple whitelist/deny-by-default HTTP API authorization policy.
#	* Refer to the data sent by Envoy in External Authorization messages.
#
# For more information see:
#
#	* Rego Rules: https://www.openpolicyagent.org/docs/latest/#rules
#	* Envoy External Authorization: https://www.envoyproxy.io/docs/envoy/latest/api-v3/service/auth/v3/external_auth.proto

# removed the package name on purpose for testing purposes (was: package envoy.http.public)

# If neither of the rules below match, `allow` is `false`.
default allow = false

# `allow` is a "rule". The simplest kind of rules in Rego are "if-then" statements
# that assign a single value to a variable. If the value is omitted, it defaults to `true`.
# In other words, this rule is equivalent to:
#
#	allow = true {
#		input.attributes.request.http.method == "GET"
#		input.attributes.request.http.path == "/"
#	}
#
# Since statements like `X = true { ... }` are so common, Rego lets you omit the `= true` bit.
#
# This rule says (in English):
#
#	allow is true if...
#		method is "GET", and...
#		path is "/"
#
# The statements in the body of the rule are AND-ed together.
allow {
	input.attributes.request.http.method == "GET"
	input.attributes.request.http.path == "/"
}

# In Rego, logical OR is expressed by defining multiple rules with the same name.
#
# This rule says (in English):
#
#	allow is true if...
#		authorization is "Basic charlie"
allow {
	input.attributes.request.http.headers.authorization == "Basic charlie"
}
