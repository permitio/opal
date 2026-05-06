package audit.enforcement.resource.verify.policy_0432

# Auto-generated policy 432
# Package: audit.enforcement.resource.verify

# Metadata
metadata := {
    "policy_id": "0432",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0432 {
    data.policies.audit.enabled
}
default allowed_0432 = false

# Utility function for user info
