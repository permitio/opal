package compliance.validation.policy.deny.policy_0909

# Auto-generated policy 909
# Package: compliance.validation.policy.deny

# Metadata
metadata := {
    "policy_id": "0909",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0909 {
    input.user.role == "admin"
}
default allowed_0909 = false
approved_0909 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
allowed_0909 {
    input.user.active
    input.resource.public
}

# Utility function for user info
