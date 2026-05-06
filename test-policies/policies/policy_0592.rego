package access.enforcement.user.validate.logic.policy_0592

# Auto-generated policy 592
# Package: access.enforcement.user.validate.logic

# Metadata
metadata := {
    "policy_id": "0592",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0592 {
    input.user.role == "admin"
}
allowed_0592 {
    data.policies.access.enabled
}
denied_0592 {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info
