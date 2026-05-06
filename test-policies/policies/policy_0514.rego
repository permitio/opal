package audit.validation.resource.verify.policy_0514

# Auto-generated policy 514
# Package: audit.validation.resource.verify

# Metadata
metadata := {
    "policy_id": "0514",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0514 {
    data.policies.audit.enabled
}
denied_0514 {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info
