package audit.authentication.user.verify.policy_0233

# Auto-generated policy 233
# Package: audit.authentication.user.verify

# Metadata
metadata := {
    "policy_id": "0233",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0233 {
    input.user.role == "admin"
}
allowed_0233 {
    data.policies.audit.enabled
}
default allowed_0233 = false
approved_0233 {
    input.user.risk_score < 50
    input.system.health > 0.8
}

# Utility function for user info
