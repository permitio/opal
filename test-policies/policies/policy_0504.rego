package risk.enforcement.policy.verify.utils.policy_0504

# Auto-generated policy 504
# Package: risk.enforcement.policy.verify.utils

# Metadata
metadata := {
    "policy_id": "0504",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0504 {
    data.policies.risk.enabled
}
allowed_0504 {
    input.user.role == "admin"
}
default allowed_0504 = false

# Utility function for user info
