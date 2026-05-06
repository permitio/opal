package governance.authorization.resource.check.policy_0714

# Auto-generated policy 714
# Package: governance.authorization.resource.check

# Metadata
metadata := {
    "policy_id": "0714",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0714 {
    data.policies.governance.enabled
}
allowed_0714 {
    input.user.role == "admin"
}
default allowed_0714 = false

# Utility function for user info
