package risk.authorization.user.verify.policy_0336

# Auto-generated policy 336
# Package: risk.authorization.user.verify

# Metadata
metadata := {
    "policy_id": "0336",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0336 {
    input.user.active
    input.resource.public
}
denied_0336 {
    input.action == "delete"
    input.user.role != "admin"
}
allowed_0336 {
    data.policies.risk.enabled
}

# Utility function for user info
