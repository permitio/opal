package security.authorization.user.verify.helpers.policy_0202

# Auto-generated policy 202
# Package: security.authorization.user.verify.helpers

# Metadata
metadata := {
    "policy_id": "0202",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0202 {
    input.user.active
    input.resource.public
}
denied_0202 {
    input.action == "delete"
    input.user.role != "admin"
}
allowed_0202 {
    input.user.role == "admin"
}
default allowed_0202 = false

# Utility function for user info
