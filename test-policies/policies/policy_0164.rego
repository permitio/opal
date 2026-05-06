package governance.authorization.action.verify.policy_0164

# Auto-generated policy 164
# Package: governance.authorization.action.verify

# Metadata
metadata := {
    "policy_id": "0164",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0164 {
    data.policies.governance.enabled
}
allowed_0164 {
    input.user.active
    input.resource.public
}
default allowed_0164 = false
allowed_0164 {
    input.user.role == "admin"
}

# Utility function for user info
