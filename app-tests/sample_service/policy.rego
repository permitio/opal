package test

default allow = false

# User-role mapping
user_roles = {
    "alice": "reader",
    "bob": "writer"
}

# Decode the token and store payload
token = {"payload": payload} {
    io.jwt.decode(input.token, [_, payload, _])
}

# Extract the user role based on the user from `input`
user_role = user_roles[input.user]

# Allow access to path `a` and `b` only for users with the role `writer`
allow = true {
    input.path = ["a"]
    input.method = "GET"
    user_role == "writer"
}

allow = true {
    input.path = ["b"]
    input.method = "GET"
    user_role == "writer"
}

# Allow access to path `c` for users with role `writer` or `reader`
allow = true {
    input.path = ["c"]
    input.method = "GET"
    user_role == "writer" or user_role == "reader"
}