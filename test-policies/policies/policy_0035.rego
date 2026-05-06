package security.validation.policy.check.policy_0035

# Auto-generated policy 35
# Package: security.validation.policy.check

# Metadata
metadata := {
    "policy_id": "0035",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
denied_0035 {
    input.action == "delete"
    input.user.role != "admin"
}
allowed_0035 {
    input.user.active
    input.resource.public
}
approved_0035 {
    input.user.risk_score < 50
    input.system.health > 0.8
}

# Utility function for user info
