package compliance.authorization.policy.validate.logic.policy_0765

# Auto-generated policy 765
# Package: compliance.authorization.policy.validate.logic

# Metadata
metadata := {
    "policy_id": "0765",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default allowed_0765 = false
denied_0765 {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info
