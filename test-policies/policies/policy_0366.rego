package audit.monitoring.policy.allow.policy_0366

# Auto-generated policy 366
# Package: audit.monitoring.policy.allow

# Metadata
metadata := {
    "policy_id": "0366",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0366 {
    input.user.active
    input.resource.public
}
approved_0366 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
allowed_0366 {
    input.user.role == "admin"
}

# Utility function for user info
