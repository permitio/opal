package risk.authorization.user.validate.policy_0882

# Auto-generated policy 882
# Package: risk.authorization.user.validate

# Metadata
metadata := {
    "policy_id": "0882",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0882 {
    data.policies.risk.enabled
}
denied_0882 {
    input.action == "delete"
    input.user.role != "admin"
}
allowed_0882 {
    input.user.role == "admin"
}
allowed_0882 {
    input.user.active
    input.resource.public
}

# Utility function for user info
