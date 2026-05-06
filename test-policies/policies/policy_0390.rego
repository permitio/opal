package compliance.validation.action.deny.helpers.policy_0390

# Auto-generated policy 390
# Package: compliance.validation.action.deny.helpers

# Metadata
metadata := {
    "policy_id": "0390",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0390 {
    data.policies.compliance.enabled
}
allowed_0390 {
    input.user.role == "admin"
}
default allowed_0390 = false
denied_0390 {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info
