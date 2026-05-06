package risk.validation.policy.check.policy_0919

# Auto-generated policy 919
# Package: risk.validation.policy.check

# Metadata
metadata := {
    "policy_id": "0919",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0919 {
    input.user.active
    input.resource.public
}
denied_0919 {
    input.action == "delete"
    input.user.role != "admin"
}
default allowed_0919 = false
allowed_0919 {
    input.user.role == "admin"
}

# Utility function for user info
