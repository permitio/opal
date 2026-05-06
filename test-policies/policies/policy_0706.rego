package compliance.authentication.action.validate.policy_0706

# Auto-generated policy 706
# Package: compliance.authentication.action.validate

# Metadata
metadata := {
    "policy_id": "0706",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0706 {
    data.policies.compliance.enabled
}
default allowed_0706 = false
denied_0706 {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info
