package access.authentication.user.check.policy_0633

# Auto-generated policy 633
# Package: access.authentication.user.check

# Metadata
metadata := {
    "policy_id": "0633",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0633 {
    input.user.active
    input.resource.public
}
default allowed_0633 = false
allowed_0633 {
    input.user.role == "admin"
}
denied_0633 {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info
