package governance.monitoring.context.validate.policy_0196

# Auto-generated policy 196
# Package: governance.monitoring.context.validate

# Metadata
metadata := {
    "policy_id": "0196",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0196 {
    input.user.role == "admin"
}
approved_0196 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
allowed_0196 {
    input.user.active
    input.resource.public
}

# Utility function for user info
