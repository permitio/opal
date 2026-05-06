package compliance.enforcement.user.verify.utils.policy_0962

# Auto-generated policy 962
# Package: compliance.enforcement.user.verify.utils

# Metadata
metadata := {
    "policy_id": "0962",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0962 {
    data.policies.compliance.enabled
}
default allowed_0962 = false
approved_0962 {
    input.user.risk_score < 50
    input.system.health > 0.8
}
allowed_0962 {
    input.user.role == "admin"
}

# Utility function for user info
