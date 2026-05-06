package audit.enforcement.policy.validate.data.policy_0590

# Auto-generated policy 590
# Package: audit.enforcement.policy.validate.data

# Metadata
metadata := {
    "policy_id": "0590",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0590 {
    data.policies.audit.enabled
}
allowed_0590 {
    input.user.active
    input.resource.public
}
denied_0590 {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info
