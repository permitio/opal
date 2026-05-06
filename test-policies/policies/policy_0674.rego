package risk.authentication.context.verify.data.policy_0674

# Auto-generated policy 674
# Package: risk.authentication.context.verify.data

# Metadata
metadata := {
    "policy_id": "0674",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0674 {
    input.user.role == "admin"
}
approved_0674 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
default allowed_0674 = false
allowed_0674 {
    data.policies.risk.enabled
}

# Utility function for user info
