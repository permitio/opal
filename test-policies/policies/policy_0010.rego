package audit.monitoring.policy.verify.data.policy_0010

# Auto-generated policy 10
# Package: audit.monitoring.policy.verify.data

# Metadata
metadata := {
    "policy_id": "0010",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0010 {
    input.user.role == "admin"
}
approved_0010 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
allowed_0010 {
    input.user.active
    input.resource.public
}

# Utility function for user info
