package access.validation.policy.verify.helpers.policy_0145

# Auto-generated policy 145
# Package: access.validation.policy.verify.helpers

# Metadata
metadata := {
    "policy_id": "0145",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
denied_0145 {
    input.action == "delete"
    input.user.role != "admin"
}
allowed_0145 {
    input.user.active
    input.resource.public
}
allowed_0145 {
    input.user.role == "admin"
}
default allowed_0145 = false

# Utility function for user info
