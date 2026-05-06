package access.monitoring.resource.verify.policy_0083

# Auto-generated policy 83
# Package: access.monitoring.resource.verify

# Metadata
metadata := {
    "policy_id": "0083",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0083 {
    input.user.active
    input.resource.public
}
allowed_0083 {
    input.user.role == "admin"
}
default allowed_0083 = false
approved_0083 {
    input.user.risk_score < 50
    input.system.health > 0.8
}

# Utility function for user info
