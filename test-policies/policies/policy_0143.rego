package risk.authentication.resource.verify.utils.policy_0143

# Auto-generated policy 143
# Package: risk.authentication.resource.verify.utils

# Metadata
metadata := {
    "policy_id": "0143",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0143 {
    input.user.role == "admin"
}
allowed_0143 {
    data.policies.risk.enabled
}

# Utility function for user info
