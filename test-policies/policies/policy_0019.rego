package compliance.authorization.action.allow.policy_0019

# Auto-generated policy 19
# Package: compliance.authorization.action.allow

# Metadata
metadata := {
    "policy_id": "0019",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default allowed_0019 = false
denied_0019 {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info
