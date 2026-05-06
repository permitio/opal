package governance.validation.policy.validate.data.policy_0222

# Auto-generated policy 222
# Package: governance.validation.policy.validate.data

# Metadata
metadata := {
    "policy_id": "0222",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
approved_0222 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
allowed_0222 {
    input.user.active
    input.resource.public
}
denied_0222 {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info
