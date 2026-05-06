package risk.authentication.context.verify.utils.policy_0417

# Auto-generated policy 417
# Package: risk.authentication.context.verify.utils

# Metadata
metadata := {
    "policy_id": "0417",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0417 {
    data.policies.risk.enabled
}
allowed_0417 {
    input.user.role == "admin"
}
allowed_0417 {
    input.user.active
    input.resource.public
}

# Utility function for user info
