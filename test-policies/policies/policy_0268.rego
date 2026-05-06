package governance.enforcement.user.verify.policy_0268

# Auto-generated policy 268
# Package: governance.enforcement.user.verify

# Metadata
metadata := {
    "policy_id": "0268",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0268 {
    input.user.role == "admin"
}
allowed_0268 {
    data.policies.governance.enabled
}
denied_0268 {
    input.action == "delete"
    input.user.role != "admin"
}

# Utility function for user info
