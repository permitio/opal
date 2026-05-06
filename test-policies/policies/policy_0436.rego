package risk.authentication.user.allow.utils.policy_0436

# Auto-generated policy 436
# Package: risk.authentication.user.allow.utils

# Metadata
metadata := {
    "policy_id": "0436",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0436 {
    input.user.active
    input.resource.public
}
allowed_0436 {
    input.user.role == "admin"
}
allowed_0436 {
    data.policies.risk.enabled
}

# Utility function for user info
