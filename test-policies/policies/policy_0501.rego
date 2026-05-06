package security.authorization.user.deny.policy_0501

# Auto-generated policy 501
# Package: security.authorization.user.deny

# Metadata
metadata := {
    "policy_id": "0501",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0501 {
    data.policies.security.enabled
}
allowed_0501 {
    input.user.active
    input.resource.public
}
allowed_0501 {
    input.user.role == "admin"
}
approved_0501 {
    input.user.risk_score < 50
    input.system.health > 0.8
}

# Utility function for user info
