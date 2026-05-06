package compliance.authorization.user.allow.data.policy_0251

# Auto-generated policy 251
# Package: compliance.authorization.user.allow.data

# Metadata
metadata := {
    "policy_id": "0251",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0251 {
    input.user.active
    input.resource.public
}
default allowed_0251 = false
approved_0251 {
    input.user.risk_score < 50
    input.system.health > 0.8
}

# Utility function for user info
