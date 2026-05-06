package governance.monitoring.context.verify.data.policy_0983

# Auto-generated policy 983
# Package: governance.monitoring.context.verify.data

# Metadata
metadata := {
    "policy_id": "0983",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0983 {
    input.user.role == "admin"
}
allowed_0983 {
    data.policies.governance.enabled
}

# Utility function for user info
