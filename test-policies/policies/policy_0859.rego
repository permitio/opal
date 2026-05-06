package security.monitoring.user.deny.utils.policy_0859

# Auto-generated policy 859
# Package: security.monitoring.user.deny.utils

# Metadata
metadata := {
    "policy_id": "0859",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0859 {
    input.user.role == "admin"
}
allowed_0859 {
    input.user.active
    input.resource.public
}
approved_0859 {
    input.user.risk_score < 50
    input.system.health > 0.8
}

# Utility function for user info
