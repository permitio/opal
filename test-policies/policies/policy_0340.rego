package access.monitoring.resource.verify.policy_0340

# Auto-generated policy 340
# Package: access.monitoring.resource.verify

# Metadata
metadata := {
    "policy_id": "0340",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
approved_0340 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
allowed_0340 {
    input.user.active
    input.resource.public
}
allowed_0340 {
    input.user.role == "admin"
}
default allowed_0340 = false

# Utility function for user info
