package security.authorization.user.verify.helpers.policy_0463

# Auto-generated policy 463
# Package: security.authorization.user.verify.helpers

# Metadata
metadata := {
    "policy_id": "0463",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0463 {
    input.user.active
    input.resource.public
}
default allowed_0463 = false
allowed_0463 {
    input.user.role == "admin"
}
denied_0463 {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info
