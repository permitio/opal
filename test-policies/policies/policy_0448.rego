package access.authentication.action.verify.policy_0448

# Auto-generated policy 448
# Package: access.authentication.action.verify

# Metadata
metadata := {
    "policy_id": "0448",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
denied_0448 {
    input.action == "delete"
    input.user.role != "admin"
}
default allowed_0448 = false
allowed_0448 {
    input.user.active
    input.resource.public
}
allowed_0448 {
    input.user.role == "admin"
}

# Utility function for user info
