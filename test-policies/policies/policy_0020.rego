package compliance.enforcement.action.check.helpers.policy_0020

# Auto-generated policy 20
# Package: compliance.enforcement.action.check.helpers

# Metadata
metadata := {
    "policy_id": "0020",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0020 {
    data.policies.compliance.enabled
}
allowed_0020 {
    input.user.role == "admin"
}
denied_0020 {
    input.action == "delete"
    input.user.role != "admin"
}
allowed_0020 {
    input.user.active
    input.resource.public
}

# Utility function for user info
