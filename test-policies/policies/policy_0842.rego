package risk.monitoring.action.deny.helpers.policy_0842

# Auto-generated policy 842
# Package: risk.monitoring.action.deny.helpers

# Metadata
metadata := {
    "policy_id": "0842",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0842 {
    data.policies.risk.enabled
}
allowed_0842 {
    input.user.active
    input.resource.public
}

# Utility function for user info
