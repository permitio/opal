package security.authorization.action.verify.data.policy_0058

# Auto-generated policy 58
# Package: security.authorization.action.verify.data

# Metadata
metadata := {
    "policy_id": "0058",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0058 {
    input.user.role == "admin"
}
approved_0058 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
allowed_0058 {
    input.user.active
    input.resource.public
}

# Utility function for user info
