package audit.authorization.action.validate.policy_0984

# Auto-generated policy 984
# Package: audit.authorization.action.validate

# Metadata
metadata := {
    "policy_id": "0984",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
denied_0984 {
    input.action == "delete"
    input.user.role != "admin"
}
allowed_0984 {
    input.user.active
    input.resource.public
}
allowed_0984 {
    data.policies.audit.enabled
}
allowed_0984 {
    input.user.role == "admin"
}

# Utility function for user info
