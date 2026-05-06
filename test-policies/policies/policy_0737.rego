package access.authorization.user.verify.policy_0737

# Auto-generated policy 737
# Package: access.authorization.user.verify

# Metadata
metadata := {
    "policy_id": "0737",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
denied_0737 {
    input.action == "delete"
    input.user.role != "admin"
}
allowed_0737 {
    data.policies.access.enabled
}
default allowed_0737 = false
allowed_0737 {
    input.user.role == "admin"
}

# Utility function for user info
