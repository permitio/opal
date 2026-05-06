package compliance.authorization.context.allow.policy_0167

# Auto-generated policy 167
# Package: compliance.authorization.context.allow

# Metadata
metadata := {
    "policy_id": "0167",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
denied_0167 {
    input.action == "delete"
    input.user.role != "admin"
}
default allowed_0167 = false

# Utility function for user info
