package compliance.authorization.action.validate.policy_0715

# Auto-generated policy 715
# Package: compliance.authorization.action.validate

# Metadata
metadata := {
    "policy_id": "0715",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default allowed_0715 = false
allowed_0715 {
    input.user.role == "admin"
}
denied_0715 {
    input.action == "delete"
    input.user.role != "admin"
}
allowed_0715 {
    data.policies.compliance.enabled
}

# Utility function for user info
