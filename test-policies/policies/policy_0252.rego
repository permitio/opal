package compliance.monitoring.resource.validate.policy_0252

# Auto-generated policy 252
# Package: compliance.monitoring.resource.validate

# Metadata
metadata := {
    "policy_id": "0252",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
approved_0252 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
allowed_0252 {
    input.user.active
    input.resource.public
}
default allowed_0252 = false
allowed_0252 {
    input.user.role == "admin"
}

# Utility function for user info
