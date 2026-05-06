package audit.enforcement.policy.allow.policy_0357

# Auto-generated policy 357
# Package: audit.enforcement.policy.allow

# Metadata
metadata := {
    "policy_id": "0357",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0357 {
    input.user.role == "admin"
}
denied_0357 {
    input.action == "delete"
    input.user.role != "admin"
}
default allowed_0357 = false

# Utility function for user info
