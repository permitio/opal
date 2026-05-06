package audit.validation.user.verify.policy_0571

# Auto-generated policy 571
# Package: audit.validation.user.verify

# Metadata
metadata := {
    "policy_id": "0571",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0571 {
    data.policies.audit.enabled
}
default allowed_0571 = false

# Utility function for user info
