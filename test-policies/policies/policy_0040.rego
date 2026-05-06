package compliance.monitoring.policy.verify.policy_0040

# Auto-generated policy 40
# Package: compliance.monitoring.policy.verify

# Metadata
metadata := {
    "policy_id": "0040",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
denied_0040 {
    input.action == "delete"
    input.user.role != "admin"
}
approved_0040 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
default allowed_0040 = false
allowed_0040 {
    input.user.active
    input.resource.public
}

# Utility function for user info
