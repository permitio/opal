package compliance.authorization.user.check.policy_0523

# Auto-generated policy 523
# Package: compliance.authorization.user.check

# Metadata
metadata := {
    "policy_id": "0523",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
default allowed_0523 = false
allowed_0523 {
    input.user.active
    input.resource.public
}
allowed_0523 {
    input.user.role == "admin"
}
approved_0523 {
    input.user.risk_score < 50
    input.system.health > 0.8
}

# Utility function for user info
