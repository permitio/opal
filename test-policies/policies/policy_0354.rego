package governance.enforcement.action.validate.policy_0354

# Auto-generated policy 354
# Package: governance.enforcement.action.validate

# Metadata
metadata := {
    "policy_id": "0354",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
denied_0354 {
    input.action == "delete"
    input.user.role != "admin"
}
allowed_0354 {
    input.user.role == "admin"
}

# Utility function for user info
