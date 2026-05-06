package risk.validation.resource.check.utils.policy_0736

# Auto-generated policy 736
# Package: risk.validation.resource.check.utils

# Metadata
metadata := {
    "policy_id": "0736",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default allowed_0736 = false
allowed_0736 {
    input.user.role == "admin"
}
denied_0736 {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info
