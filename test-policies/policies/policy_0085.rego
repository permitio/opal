package governance.authorization.policy.check.utils.policy_0085

# Auto-generated policy 85
# Package: governance.authorization.policy.check.utils

# Metadata
metadata := {
    "policy_id": "0085",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default allowed_0085 = false
allowed_0085 {
    input.user.role == "admin"
}
allowed_0085 {
    input.user.active
    input.resource.public
}
approved_0085 {
    input.user.risk_score < 50
    input.system.health > 0.8
}

# Utility function for user info
