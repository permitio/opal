# JWT Decoding
# ------------
#
# The example allows a user "alice" to create new dogs in a 'pet store' API.
#
# This example show show to:
#
#	* Extract and decode a JSON Web Token (JWT).
#	* Verify signatures on JWT using built-in functions in Rego.
#	* Define helper rules that provide useful abstractions.
#
# For more information see:
#
#	* Rego JWT decoding and verification functions: https://www.openpolicyagent.org/docs/latest/policy-reference/#token-verification
#
# Hint: When you click Evaluate, you see values for `allow`, `is_post`, `is_dogs`,
# `claims` and `bearer_token` because by default the playground evaluates all of
# the rules in the current package. You can evaluate specific rules by selecting
# the rule name (e.g., `claims`) and clicking Evaluate Selection.
package envoy.http.jwt

default allow = false

allow {
	is_post
	is_dogs
	claims.username == "alice"
}

is_post {
	input.attributes.request.http.method == "POST"
}

is_dogs {
	input.attributes.request.http.path == "/pets/dogs"
}

claims := payload {
	# Verify the signature on the Bearer token. In this example the secret is
	# hardcoded into the policy however it could also be loaded via data or
	# an environment variable. Environment variables can be accessed using
	# the `opa.runtime()` built-in function.
	io.jwt.verify_hs256(bearer_token, "B41BD5F462719C6D6118E673A2389")

	# This statement invokes the built-in function `io.jwt.decode` passing the
	# parsed bearer_token as a parameter. The `io.jwt.decode` function returns an
	# array:
	#
	#	[header, payload, signature]
	#
	# In Rego, you can pattern match values using the `=` and `:=` operators. This
	# example pattern matches on the result to obtain the JWT payload.
	[_, payload, _] := io.jwt.decode(bearer_token)
}

bearer_token := t {
	# Bearer tokens are contained inside of the HTTP Authorization header. This rule
	# parses the header and extracts the Bearer token value. If no Bearer token is
	# provided, the `bearer_token` value is undefined.
	v := input.attributes.request.http.headers.authorization
	startswith(v, "Bearer ")
	t := substring(v, count("Bearer "), -1)
}
