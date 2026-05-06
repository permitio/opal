package compliance.authentication.action.check.policy_0646

# Auto-generated policy 646
# Package: compliance.authentication.action.check

# Metadata
metadata := {
    "policy_id": "0646",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0646 {
    input.user.active
    input.resource.public
}
default allowed_0646 = false
denied_0646 {
    input.action == "delete"
    input.user.role != "admin"
}
allowed_0646 {
    data.policies.compliance.enabled
}

# Utility function for user info
