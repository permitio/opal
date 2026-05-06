package risk.authentication.context.deny.policy_0241

# Auto-generated policy 241
# Package: risk.authentication.context.deny

# Metadata
metadata := {
    "policy_id": "0241",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0241 {
    input.user.role == "admin"
}
allowed_0241 {
    input.user.active
    input.resource.public
}
allowed_0241 {
    data.policies.risk.enabled
}

# Utility function for user info
