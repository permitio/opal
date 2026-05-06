package compliance.authentication.action.deny.data.policy_0520

# Auto-generated policy 520
# Package: compliance.authentication.action.deny.data

# Metadata
metadata := {
    "policy_id": "0520",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default allowed_0520 = false
allowed_0520 {
    data.policies.compliance.enabled
}
allowed_0520 {
    input.user.role == "admin"
}
denied_0520 {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info
