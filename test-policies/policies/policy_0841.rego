package audit.authentication.action.verify.logic.policy_0841

# Auto-generated policy 841
# Package: audit.authentication.action.verify.logic

# Metadata
metadata := {
    "policy_id": "0841",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0841 {
    input.user.active
    input.resource.public
}
allowed_0841 {
    data.policies.audit.enabled
}
denied_0841 {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info
