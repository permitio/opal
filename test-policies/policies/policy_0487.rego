package audit.authentication.action.verify.policy_0487

# Auto-generated policy 487
# Package: audit.authentication.action.verify

# Metadata
metadata := {
    "policy_id": "0487",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
denied_0487 {
    input.action == "delete"
    input.user.role != "admin"
}
allowed_0487 {
    input.user.active
    input.resource.public
}
allowed_0487 {
    data.policies.audit.enabled
}
allowed_0487 {
    input.user.role == "admin"
}

# Utility function for user info
